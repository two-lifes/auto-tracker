"""Background loop. Stage 0: version notices; reminders join it in stage 6."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.clock import utcnow
from bot.db.models import User
from bot.services.deployments import pending_deployments
from bot.views import deployment_text

log = logging.getLogger(__name__)

TICK_SECONDS = 60
_RETRYABLE = (TelegramNetworkError, TelegramRetryAfter, TelegramServerError)


async def deliver_deployments(session_factory: async_sessionmaker, bot: Bot, now: datetime) -> None:
    async with session_factory() as session:
        deployments = await pending_deployments(session)
        if not deployments:
            return
        users = list(await session.scalars(select(User)))
        if not users:
            return  # a fresh DB has no user until /start
        for d in deployments:
            try:
                for user in users:
                    await bot.send_message(user.tg_id, deployment_text(d))
            except (TelegramForbiddenError, TelegramBadRequest):
                log.exception("Dropping deployment notice %s", d.id)
            except _RETRYABLE as exc:
                log.warning("Telegram unavailable (%s); will retry", exc)
                return
            d.notified_at = now
            await session.commit()


async def tick(
    session_factory: async_sessionmaker, bot: Bot, now: datetime, db_lock: asyncio.Lock
) -> None:
    # Same lock as update handlers: no lost updates or "database is locked" between them
    async with db_lock:
        await deliver_deployments(session_factory, bot, now)


async def run_scheduler(
    session_factory: async_sessionmaker,
    bot: Bot,
    db_lock: asyncio.Lock,
    clock: Callable[[], datetime] = utcnow,
    interval: float = TICK_SECONDS,
) -> None:
    while True:
        try:
            await tick(session_factory, bot, clock(), db_lock)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One bad tick must not stop the loop for good
            log.exception("Scheduler tick failed")
        await asyncio.sleep(interval)
