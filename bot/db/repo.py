from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Settings, User

DEFAULT_CURRENCY = "RUB"


async def get_or_create_user(
    session: AsyncSession, tg_id: int, name: str | None, now: datetime, default_tz: str
) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(tg_id=tg_id, name=name, created_at=now)
        session.add(user)
        await session.flush()
    if await session.get(Settings, user.id) is None:
        # Owners from stage 0 have no settings row yet
        session.add(Settings(user_id=user.id, timezone=default_tz, currency=DEFAULT_CURRENCY))
        await session.flush()
    return user


async def get_settings(session: AsyncSession, user: User) -> Settings:
    return await session.get(Settings, user.id)
