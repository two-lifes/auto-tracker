from datetime import UTC, datetime

import pytest

from bot import clock
from tests.harness import check_telegram_html, make_harness

# 17.10.2026 is a Saturday; 07:00 UTC is 10:00 in Moscow
NOW = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)


@pytest.fixture
def now():
    """A controllable clock: ``now.set(datetime)`` moves time for the bot."""

    class Clock:
        value = NOW

        def set(self, value: datetime) -> None:
            self.value = value

    c = Clock()
    clock.set_clock(lambda: c.value)
    yield c
    clock.set_clock(lambda: datetime.now(UTC))


@pytest.fixture
async def h(tmp_path, now):
    harness, engine = await make_harness(tmp_path / "t.db", now)
    yield harness
    # Telegram rejects the whole message on broken markup
    for text in harness.net.texts():
        check_telegram_html(text)
    await engine.dispose()
