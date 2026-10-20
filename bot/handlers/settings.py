"""⚙️ Настройки: time zone and currency (part of FR-9; the rest comes with stages 6–7)."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import views
from bot.clock import utcnow
from bot.db.models import User
from bot.db.repo import get_settings
from bot.handlers.common import ANSWER, show
from bot.keyboards import MENU_SETTINGS
from bot.keyboards.settings import SetCb, currency_keyboard, settings_keyboard, tz_keyboard
from bot.services.parse import InvalidInput, parse_currency

router = Router(name="settings")


class SettingsForm(StatesGroup):
    timezone = State()
    currency = State()


def _valid_tz(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


async def _screen(session: AsyncSession, user: User, prefix: str = "") -> str:
    current = await get_settings(session, user)
    return views.with_header(prefix, views.settings_text(current, utcnow()))


@router.message(Command("settings"))
@router.message(F.text == MENU_SETTINGS)
async def settings(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    await message.answer(await _screen(session, user), reply_markup=settings_keyboard())


@router.callback_query(SetCb.filter(F.action == "tz"))
async def ask_tz(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.timezone)
    await show(callback, views.TZ_PROMPT, tz_keyboard())


@router.callback_query(SetCb.filter(F.action == "currency"))
async def ask_currency(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.currency)
    await show(callback, views.CURRENCY_PROMPT, currency_keyboard())


async def _save(
    target: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    **values: str,
) -> None:
    s = await get_settings(session, user)
    for name, value in values.items():
        setattr(s, name, value)
    await session.flush()
    await state.clear()
    text = await _screen(session, user, views.SAVED)
    if isinstance(target, CallbackQuery):
        await show(target, text, settings_keyboard())
    else:
        await target.answer(text, reply_markup=settings_keyboard())


@router.callback_query(SetCb.filter(F.action.in_({"tz_pick", "currency_pick"})))
async def picked(
    callback: CallbackQuery,
    callback_data: SetCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    if callback_data.action == "tz_pick":
        if not _valid_tz(callback_data.arg):
            await callback.answer(views.STALE_BUTTON)
            return
        await _save(callback, state, session, user, timezone=callback_data.arg)
    else:
        await _save(callback, state, session, user, currency=parse_currency(callback_data.arg))


@router.message(StateFilter(SettingsForm.timezone), ANSWER)
async def typed_tz(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    name = message.text.strip()
    if not _valid_tz(name):
        await message.answer(views.TZ_UNKNOWN, reply_markup=tz_keyboard())
        return
    await _save(message, state, session, user, timezone=name)


@router.message(StateFilter(SettingsForm.currency), ANSWER)
async def typed_currency(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    try:
        code = parse_currency(message.text)
    except InvalidInput:
        await message.answer(views.CURRENCY_BAD, reply_markup=currency_keyboard())
        return
    await _save(message, state, session, user, currency=code)
