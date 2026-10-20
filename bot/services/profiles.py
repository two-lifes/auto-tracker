"""Car profiles and their odometer readings (FR-2, FR-3) on top of the DB."""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    PROFILE_ACTIVE,
    PROFILE_ARCHIVED,
    SOURCE_MANUAL,
    OdometerReading,
    Profile,
    User,
)
from bot.services.mileage import Reading, Violation, check_reading, current_mileage

# Optional profile fields in the order the creation dialog asks for them (D-12)
OPTIONAL_FIELDS = ("make", "model", "year", "plate", "vin", "engine", "purchase_date", "note")
EDITABLE_FIELDS = ("name", "initial_mileage", *OPTIONAL_FIELDS)


async def list_profiles(session: AsyncSession, user: User, status: str) -> list[Profile]:
    rows = await session.scalars(
        select(Profile)
        .where(Profile.user_id == user.id, Profile.status == status)
        .order_by(Profile.id)
    )
    return list(rows)


async def has_any(session: AsyncSession, user: User) -> bool:
    """Archived cars count too: the owner is not new then."""
    found = await session.scalar(select(Profile.id).where(Profile.user_id == user.id).limit(1))
    return found is not None


async def get_profile(session: AsyncSession, user: User, profile_id: int) -> Profile | None:
    """None for someone else's or deleted profile: old buttons must not reach them."""
    profile = await session.get(Profile, profile_id)
    return profile if profile is not None and profile.user_id == user.id else None


async def active_profile(session: AsyncSession, user: User) -> Profile | None:
    if user.active_profile_id is None:
        return None
    return await get_profile(session, user, user.active_profile_id)


async def name_taken(
    session: AsyncSession, user: User, name: str, exclude_id: int | None = None
) -> bool:
    # SQLite lower() folds ASCII only, so compare in Python: names are Cyrillic
    names = await session.execute(
        select(Profile.id, Profile.name).where(Profile.user_id == user.id)
    )
    folded = name.casefold()
    return any(pid != exclude_id and n.casefold() == folded for pid, n in names)


async def create_profile(
    session: AsyncSession, user: User, values: dict, now: datetime
) -> Profile:
    """The new car becomes the active one: it is what the owner is about to work with."""
    profile = Profile(
        user_id=user.id,
        status=PROFILE_ACTIVE,
        created_at=now,
        updated_at=now,
        **{k: values.get(k) for k in EDITABLE_FIELDS},
    )
    session.add(profile)
    await session.flush()
    user.active_profile_id = profile.id
    await session.flush()
    return profile


async def update_field(
    session: AsyncSession, profile: Profile, field: str, value, now: datetime
) -> None:
    assert field in EDITABLE_FIELDS, field
    setattr(profile, field, value)
    profile.updated_at = now
    await session.flush()


async def set_active(session: AsyncSession, user: User, profile: Profile) -> None:
    user.active_profile_id = profile.id
    await session.flush()


async def _pick_another_active(session: AsyncSession, user: User, gone: Profile) -> None:
    if user.active_profile_id != gone.id:
        return
    others = [p for p in await list_profiles(session, user, PROFILE_ACTIVE) if p.id != gone.id]
    user.active_profile_id = others[0].id if others else None


async def archive(session: AsyncSession, user: User, profile: Profile, now: datetime) -> None:
    await _pick_another_active(session, user, profile)
    profile.status = PROFILE_ARCHIVED
    profile.updated_at = now
    await session.flush()


async def restore(session: AsyncSession, user: User, profile: Profile, now: datetime) -> None:
    profile.status = PROFILE_ACTIVE
    profile.updated_at = now
    if user.active_profile_id is None:
        user.active_profile_id = profile.id
    await session.flush()


async def delete(session: AsyncSession, user: User, profile: Profile) -> None:
    """Readings go with the profile (ON DELETE CASCADE)."""
    await _pick_another_active(session, user, profile)
    await session.flush()
    await session.delete(profile)
    await session.flush()


# --- readings ---


async def readings_of(session: AsyncSession, profile: Profile) -> list[OdometerReading]:
    """Newest first, the way the history shows them."""
    rows = await session.scalars(
        select(OdometerReading)
        .where(OdometerReading.profile_id == profile.id)
        .order_by(OdometerReading.date.desc(), OdometerReading.value.desc())
    )
    return list(rows)


def as_rules(rows: list[OdometerReading]) -> list[Reading]:
    return [Reading(r.id, r.date, r.value) for r in rows]


async def current_of(session: AsyncSession, profile: Profile) -> int:
    return current_mileage(as_rules(await readings_of(session, profile)), profile.initial_mileage)


async def count_readings(session: AsyncSession, profile: Profile) -> int:
    return await session.scalar(
        select(func.count()).where(OdometerReading.profile_id == profile.id)
    )


async def get_reading(
    session: AsyncSession, profile: Profile, reading_id: int
) -> OdometerReading | None:
    reading = await session.get(OdometerReading, reading_id)
    return reading if reading is not None and reading.profile_id == profile.id else None


async def check(
    session: AsyncSession,
    profile: Profile,
    day: date,
    value: int,
    exclude_id: int | None = None,
) -> Violation | None:
    rows = as_rules(await readings_of(session, profile))
    return check_reading(rows, profile.initial_mileage, day, value, exclude_id)


async def add_reading(
    session: AsyncSession, profile: Profile, day: date, value: int, now: datetime
) -> OdometerReading:
    """Callers check the rules first (``check``), so the owner sees why a value is wrong."""
    reading = OdometerReading(
        profile_id=profile.id, date=day, value=value, source=SOURCE_MANUAL, created_at=now
    )
    session.add(reading)
    await session.flush()
    return reading


async def update_reading(
    session: AsyncSession, reading: OdometerReading, day: date, value: int
) -> None:
    reading.date, reading.value = day, value
    await session.flush()


async def delete_reading(session: AsyncSession, reading: OdometerReading) -> None:
    await session.delete(reading)
    await session.flush()
