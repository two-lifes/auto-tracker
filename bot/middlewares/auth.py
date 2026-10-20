import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

log = logging.getLogger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    """Drops every update that does not come from a whitelisted user (FR-1)."""

    def __init__(self, allowed_user_ids: Iterable[int]) -> None:
        self.allowed_user_ids = frozenset(allowed_user_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or user.id not in self.allowed_user_ids:
            log.info("Ignored update from user %s", user.id if user else None)
            return None
        return await handler(event, data)
