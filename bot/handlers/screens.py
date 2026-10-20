"""Screens of the 🚗 Авто section, shared by its handlers and the profile dialog."""

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot import views
from bot.db.models import PROFILE_ACTIVE, PROFILE_ARCHIVED, Profile, User
from bot.keyboards.cars import archive_keyboard, card_keyboard, cars_keyboard
from bot.services import profiles

Screen = tuple[str, InlineKeyboardMarkup]


async def cars_screen(session: AsyncSession, user: User, prefix: str = "") -> Screen:
    """One car: its card right away. Several: a list to switch between them (FR-2.4)."""
    active = await profiles.list_profiles(session, user, PROFILE_ACTIVE)
    archived = len(await profiles.list_profiles(session, user, PROFILE_ARCHIVED))
    if len(active) == 1:
        return await card_screen(session, user, active[0], prefix)
    text = views.CARS_LIST if active else views.CARS_EMPTY
    return (
        views.with_header(prefix, text),
        cars_keyboard(active, user.active_profile_id, archived),
    )


async def card_screen(
    session: AsyncSession, user: User, profile: Profile, prefix: str = ""
) -> Screen:
    is_active = profile.id == user.active_profile_id
    several = len(await profiles.list_profiles(session, user, PROFILE_ACTIVE)) > 1
    archived = len(await profiles.list_profiles(session, user, PROFILE_ARCHIVED))
    text = views.profile_card(
        profile,
        await profiles.current_of(session, profile),
        is_active,
        await profiles.count_readings(session, profile),
    )
    return (
        views.with_header(prefix, text),
        card_keyboard(profile, is_active, with_list=several, archived=archived),
    )


async def archive_screen(session: AsyncSession, user: User, prefix: str = "") -> Screen:
    archived = await profiles.list_profiles(session, user, PROFILE_ARCHIVED)
    text = views.ARCHIVE_LIST if archived else views.ARCHIVE_EMPTY
    return (views.with_header(prefix, text), archive_keyboard(archived))
