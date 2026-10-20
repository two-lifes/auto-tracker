from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

PROFILE_ACTIVE = "active"
PROFILE_ARCHIVED = "archived"

SOURCE_MANUAL = "manual"


class Base(DeclarativeBase):
    pass


class User(Base):
    """The bot owner (see docs/04-domain-model.md, «Владелец»)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # users <-> profiles is a cycle; use_alter lets the metadata order the tables
    active_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "profiles.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_users_active_profile_id_profiles",
        )
    )


class Settings(Base):
    """One per owner. Further FR-9 fields arrive with the stages that use them."""

    __tablename__ = "settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    timezone: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3))


class Profile(Base):
    """A car. All records, mileage, photos and reminders belong to one."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Unique per owner ignoring case; checked in bot.services.profiles
    name: Mapped[str] = mapped_column(String(64))
    make: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(64))
    year: Mapped[int | None] = mapped_column(Integer)
    plate: Mapped[str | None] = mapped_column(String(16))
    vin: Mapped[str | None] = mapped_column(String(17))
    engine: Mapped[str | None] = mapped_column(String(64))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    # Lower bound for every reading, not a reading itself (D-13)
    initial_mileage: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(10), default=PROFILE_ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OdometerReading(Base):
    __tablename__ = "odometer_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    # The owner's local date: readings are compared day by day
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(10), default=SOURCE_MANUAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FsmState(Base):
    """Dialog state and entered values; survive restarts (bot.fsm.DbStorage)."""

    __tablename__ = "fsm_states"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(128))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Deployment(Base):
    """A bot version that started on the server (ok) or failed to start and was rolled back."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(40))  # git sha
    title: Mapped[str | None] = mapped_column(String(200))  # commit subject
    status: Mapped[str] = mapped_column(String(10))  # ok / failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
