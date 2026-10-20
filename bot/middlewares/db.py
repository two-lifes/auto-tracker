import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.clock import utcnow
from bot.db.repo import get_or_create_user
from bot.fsm import use_session


class DbSessionMiddleware(BaseMiddleware):
    """Gives each update its own session and the owner's User row; commits on success.

    The sessionmaker and the write lock come from dispatcher workflow data
    (``dp["sessionmaker"]``, ``dp["db_lock"]``, ``dp["default_tz"]``). The lock is shared with
    the scheduler so their writes never interleave.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sessionmaker: async_sessionmaker = data["sessionmaker"]
        db_lock: asyncio.Lock = data["db_lock"]
        tg_user = data["event_from_user"]
        async with db_lock, sessionmaker() as session, session.begin():
            data["session"] = session
            data["user"] = await get_or_create_user(
                session, tg_user.id, tg_user.full_name, utcnow(), data["default_tz"]
            )
            # Dialog state is written in the same transaction (see bot.fsm)
            with use_session(session):
                return await handler(event, data)
