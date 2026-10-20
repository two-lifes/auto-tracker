"""Dialog state in SQLite, so a restart in the middle of a dialog loses nothing.

aiogram reads the state in its own middleware before DbSessionMiddleware opens the update's
transaction, but handlers write it while that transaction may already hold SQLite's write
lock. A second connection would then wait for a lock that is released only after the
handler, so inside an update the storage uses the update's own session (``use_session``):
the state commits or rolls back together with the data it describes.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.clock import utcnow
from bot.db.models import FsmState

_update_session: ContextVar[AsyncSession | None] = ContextVar("fsm_session", default=None)


@contextmanager
def use_session(session: AsyncSession) -> Iterator[None]:
    token = _update_session.set(session)
    try:
        yield
    finally:
        _update_session.reset(token)


def storage_key(key: StorageKey) -> str:
    return ":".join(
        str(part) if part is not None else ""
        for part in (
            key.bot_id, key.chat_id, key.user_id, key.thread_id,
            key.business_connection_id, key.destiny,
        )
    )


class DbStorage(BaseStorage):
    def __init__(self, sessionmaker: async_sessionmaker | None = None) -> None:
        # Bound after the engine exists (bot.__main__) or per test DB (tests.harness)
        self.sessionmaker = sessionmaker

    async def _read(self, key: StorageKey) -> FsmState | None:
        session = _update_session.get()
        if session is not None:
            return await session.get(FsmState, storage_key(key))
        async with self.sessionmaker() as own:
            return await own.get(FsmState, storage_key(key))

    async def _write(self, key: StorageKey, **values: Any) -> None:
        session = _update_session.get()
        if session is not None:
            await self._apply(session, key, values)
            return
        async with self.sessionmaker() as own, own.begin():
            await self._apply(own, key, values)

    @staticmethod
    async def _apply(session: AsyncSession, key: StorageKey, values: dict[str, Any]) -> None:
        row = await session.get(FsmState, storage_key(key))
        state = values.get("state", row.state if row else None)
        data = values.get("data", row.data if row else {})
        if state is None and not data:
            # A finished dialog leaves nothing behind
            if row is not None:
                await session.delete(row)
                await session.flush()
            return
        if row is None:
            row = FsmState(key=storage_key(key))
            session.add(row)
        row.state, row.data, row.updated_at = state, data, utcnow()
        await session.flush()

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._write(key, state=state.state if isinstance(state, State) else state)

    async def get_state(self, key: StorageKey) -> str | None:
        row = await self._read(key)
        return row.state if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        # A new dict: SQLAlchemy does not see in-place changes of a JSON value
        await self._write(key, data=dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = await self._read(key)
        return dict(row.data) if row else {}

    async def close(self) -> None:
        pass
