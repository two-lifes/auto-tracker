from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe

from bot.db.models import Deployment
from bot.services.deployments import STATUS_FAILED, STATUS_OK, record_startup


async def _startup(h, version, title=None, failed=None):
    async with h.sessionmaker() as session, session.begin():
        await record_startup(session, version, title, failed, h.clock.value)


async def _rows(h):
    return [(d.version, d.status) for d in await h.all(Deployment)]


async def test_new_version_is_recorded_once(h):
    await _startup(h, "aaa")
    await _startup(h, "aaa")  # reboot or crash restart of the same version
    await _startup(h, "bbb", "Stage 0")
    assert await _rows(h) == [("aaa", STATUS_OK), ("bbb", STATUS_OK)]


async def test_local_run_records_nothing(h):
    await _startup(h, None)
    assert await _rows(h) == []


async def test_rollback_records_failed_version(h):
    await _startup(h, "aaa")
    # deploy.sh restarts the previous version with FAILED_VERSION set
    await _startup(h, "aaa", failed="bbb")
    await _startup(h, "aaa", failed="bbb")
    assert await _rows(h) == [("aaa", STATUS_OK), ("bbb", STATUS_FAILED)]


async def test_notice_waits_for_owner_then_sent_once(h):
    await _startup(h, "abc1234ffff", "Каркас бота")
    await h.tick()
    assert h.net.sent() == []  # no owner in a fresh DB until /start

    await h.text("/start")
    await h.tick()
    await h.tick()
    notices = [t for t in h.net.texts() if "обновлён" in t]
    assert notices == ["🔄 Бот обновлён до версии <code>abc1234</code>\nКаркас бота"]


async def test_failed_notice(h):
    await h.text("/start")
    await _startup(h, "aaa")
    await h.tick()
    await _startup(h, "aaa", failed="bbb9999")
    await h.tick()
    assert "Обновление bbb9999 не запустилось" in h.last_plain()


async def test_notice_retried_after_network_error(h):
    await h.text("/start")
    await _startup(h, "abc1234")
    h.net.fail_next = TelegramNetworkError(method=GetMe(), message="down")
    await h.tick()
    assert "обновлён" not in h.last_plain()
    await h.tick()
    assert "обновлён" in h.last_plain()
    assert all(d.notified_at is not None for d in await h.all(Deployment))


async def test_commit_title_is_escaped(h):
    await h.text("/start")
    await _startup(h, "abc1234", "Fix <menu> & help")
    await h.tick()
    assert "Fix &lt;menu&gt; &amp; help" in h.net.last_text()
