from datetime import timedelta

from aiogram.fsm.state import State, StatesGroup
from aiogram.methods import SendMessage
from aiogram.types import ReplyKeyboardMarkup

from bot import views
from bot.db.models import User
from bot.keyboards import (
    MENU_BUTTONS,
    MENU_HISTORY,
    MENU_PHOTOS,
    MENU_RECORD,
    MENU_REMINDERS,
)
from tests.harness import plain
from tests.tg_fakes import OWNER_ID, STRANGER_ID, sticker_update


class _Dialog(StatesGroup):
    # Stage 0 has no dialogs yet; a stand-in state checks that /cancel resets any of them
    step = State()


def _menu_texts(message: SendMessage) -> list[str]:
    assert isinstance(message.reply_markup, ReplyKeyboardMarkup)
    return [button.text for row in message.reply_markup.keyboard for button in row]


async def test_stranger_is_ignored(h):
    assert await h.text("/start", user_id=STRANGER_ID) is None
    assert await h.text("/status", user_id=STRANGER_ID) is None
    assert await h.all(User) == []
    assert h.net.requests == []


async def test_start_registers_owner(h):
    await h.text("/start")
    assert "Автодневник" in plain(h.net.texts()[0])
    users = await h.all(User)
    assert [(u.tg_id, u.name) for u in users] == [(OWNER_ID, "Test")]


async def test_menu_keyboard(h):
    await h.text("/menu")
    assert _menu_texts(h.net.sent()[-1]) == list(MENU_BUTTONS)


async def test_repeated_start_keeps_one_owner(h):
    await h.text("/start")
    await h.text("/start")
    assert len(await h.all(User)) == 1


async def test_menu_and_help_without_car(h):
    assert await h.text("/menu") == views.NO_CAR
    assert "/cancel" in await h.text("/help")


async def test_later_sections_are_placeholders(h):
    for button in (MENU_RECORD, MENU_HISTORY, MENU_REMINDERS, MENU_PHOTOS):
        assert await h.text(button) == views.SECTION_SOON


async def test_cancel_without_dialog(h):
    assert (await h.text("/cancel")).startswith(views.NOTHING_TO_CANCEL)


async def test_cancel_resets_dialog(h):
    state = h.dp.fsm.get_context(h.bot, chat_id=OWNER_ID, user_id=OWNER_ID)
    await state.set_state(_Dialog.step)
    assert (await h.text("/cancel")).startswith(views.CANCELLED)
    assert await state.get_state() is None


async def test_unknown_input(h):
    assert await h.text("привет") == views.NOT_UNDERSTOOD
    await h.feed(sticker_update())
    assert h.last_plain() == views.NOT_UNDERSTOOD


async def test_stale_button(h):
    await h.tap("old:button")
    await h.tap("old:button", inaccessible=True)
    assert h.net.callback_answers() == [views.STALE_BUTTON, views.STALE_BUTTON]


async def test_status_local(h, now):
    now.set(now.value + timedelta(hours=2, minutes=5))
    reply = await h.text("/status")
    assert reply == "Версия: локальная\nРаботает: 2 ч 5 мин\nПоследний бэкап: нет данных"


async def test_status_shows_short_version(h):
    h.app_version = "abc1234def5678"
    assert (await h.text("/status")).startswith("Версия: abc1234\n")


async def test_handler_error_tells_owner(h, monkeypatch):
    def broken(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(views, "status_text", broken)
    assert await h.text("/status") == views.ERROR
