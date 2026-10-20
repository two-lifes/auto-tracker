"""Runs the real dispatcher against a temporary DB and a fake Telegram network."""

import asyncio
import itertools
import re
from functools import cache
from html.parser import HTMLParser

from aiogram import Bot
from sqlalchemy import select

from bot.app import build_dispatcher
from bot.db.models import Base
from bot.db.session import create_engine, create_sessionmaker
from bot.scheduler import tick
from tests.tg_fakes import OWNER_ID, FakeSession, callback_update, text_update

TELEGRAM_TAGS = {"b", "i", "u", "s", "code", "pre", "a", "blockquote", "tg-spoiler"}


class _TagChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        assert tag in TELEGRAM_TAGS, f"<{tag}> is not Telegram HTML"
        assert not (tag == "blockquote" and "blockquote" in self.stack), "nested blockquote"
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack and self.stack[-1] == tag, f"unbalanced </{tag}>"
        self.stack.pop()


def check_telegram_html(text: str) -> None:
    checker = _TagChecker()
    checker.feed(text)
    checker.close()
    assert not checker.stack, f"unclosed {checker.stack} in {text!r}"


def plain(text: str) -> str:
    """Tests compare plain text: no HTML tags."""
    return re.sub(r"<[^>]+>", "", text)


class Harness:
    def __init__(self, dp, bot, net, sessionmaker, clock):
        self.dp, self.bot, self.net, self.sessionmaker = dp, bot, net, sessionmaker
        self.clock = clock
        self.db_lock = asyncio.Lock()
        self.started_at = clock.value
        self.app_version: str | None = None

    async def feed(self, update) -> None:
        await self.dp.feed_update(
            self.bot, update, sessionmaker=self.sessionmaker, db_lock=self.db_lock,
            started_at=self.started_at, app_version=self.app_version,
        )

    async def text(self, text: str, user_id: int = OWNER_ID) -> str | None:
        before = len(self.net.texts())
        await self.feed(text_update(text, user_id))
        return self._last_since(before)

    def _last_since(self, before: int) -> str | None:
        texts = self.net.texts()
        if len(texts) <= before:
            return None
        return plain(texts[-1])

    def last_plain(self) -> str:
        return plain(self.net.last_text())

    async def tap(self, data: str, inaccessible: bool = False) -> str | None:
        before = len(self.net.texts())
        await self.feed(callback_update(data, inaccessible=inaccessible))
        return self._last_since(before)

    async def all(self, model):
        async with self.sessionmaker() as session:
            return list(await session.scalars(select(model).order_by(model.id)))

    async def tick(self) -> None:
        await tick(self.sessionmaker, self.bot, self.clock.value, self.db_lock)


@cache
def shared_dispatcher():
    # Routers are module-level and can be attached to only one dispatcher per process
    return build_dispatcher({OWNER_ID})


# FSM state is keyed by bot id, so a fresh bot id per test isolates dialog state
_bot_ids = itertools.count(100)


async def make_harness(db_path, clock) -> tuple[Harness, object]:
    # A file DB: every update opens its own connection, and :memory: is per-connection
    engine = create_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    net = FakeSession()
    bot = Bot(token=f"{next(_bot_ids)}:TEST", session=net)
    return Harness(shared_dispatcher(), bot, net, create_sessionmaker(engine), clock), engine
