from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    """The bot owner (see docs/04-domain-model.md, «Владелец»)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Deployment(Base):
    """A bot version that started on the server (ok) or failed to start and was rolled back."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(40))  # git sha
    title: Mapped[str | None] = mapped_column(String(200))  # commit subject
    status: Mapped[str] = mapped_column(String(10))  # ok / failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
