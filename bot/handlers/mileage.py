"""🛣 Пробег: odometer readings, their history and corrections (FR-3.1–3.4)."""

import math
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import views
from bot.clock import utcnow
from bot.db.models import OdometerReading, Profile, User
from bot.handlers.common import ANSWER, send_menu, show, today
from bot.handlers.screens import Screen
from bot.keyboards import MENU_MILEAGE
from bot.keyboards.mileage import (
    KmCb,
    date_keyboard,
    edit_keyboard,
    entry_keyboard,
    history_keyboard,
    reading_delete_keyboard,
    reading_keyboard,
)
from bot.services import profiles
from bot.services.mileage import Reading, gain, monthly_average
from bot.services.parse import InvalidInput, parse_date, parse_mileage

router = Router(name="mileage")

PAGE_SIZE = 10


class Km(StatesGroup):
    value = State()
    date = State()
    edit_value = State()
    edit_date = State()


async def _profile(state: FSMContext, session: AsyncSession, user: User) -> Profile | None:
    profile_id = (await state.get_data()).get("profile_id")
    return await profiles.get_profile(session, user, profile_id) if profile_id else None


@router.message(Command("km"))
@router.message(F.text == MENU_MILEAGE)
async def entry(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    profile = await profiles.active_profile(session, user)
    if profile is None:
        await send_menu(message, session, user)
        return
    await state.set_state(Km.value)
    await state.set_data({"profile_id": profile.id})
    mileage = await profiles.current_of(session, profile)
    await message.answer(views.km_prompt(profile, mileage, None), reply_markup=entry_keyboard())


@router.callback_query(KmCb.filter(F.action == "other_date"), StateFilter(Km.value))
async def other_date(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Km.date)
    await show(callback, views.KM_DATE_PROMPT, date_keyboard())


async def _ask_value(
    target: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    day: date,
) -> None:
    profile = await _profile(state, session, user)
    if profile is None:
        await state.clear()
        await send_menu(target if isinstance(target, Message) else target.message, session, user)
        return
    await state.update_data(date=day.isoformat())
    await state.set_state(Km.value)
    text = views.km_prompt(profile, await profiles.current_of(session, profile), day)
    if isinstance(target, CallbackQuery):
        await show(target, text, edit_keyboard())
    else:
        await target.answer(text, reply_markup=edit_keyboard())


@router.callback_query(KmCb.filter(F.action == "day"), StateFilter(Km.date))
async def quick_day(
    callback: CallbackQuery,
    callback_data: KmCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    day = await today(session, user)
    if callback_data.arg == "yesterday":
        day -= timedelta(days=1)
    await _ask_value(callback, state, session, user, day)


@router.message(StateFilter(Km.date), ANSWER)
async def typed_date(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    try:
        day = parse_date(message.text, await today(session, user))
    except InvalidInput as exc:
        await message.answer(views.DATE_ERRORS[exc.reason], reply_markup=date_keyboard())
        return
    await _ask_value(message, state, session, user, day)


@router.message(StateFilter(Km.value), ANSWER)
async def typed_value(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    profile = await _profile(state, session, user)
    if profile is None:
        await state.clear()
        await send_menu(message, session, user)
        return
    try:
        value = parse_mileage(message.text)
    except InvalidInput as exc:
        text = f"{views.MILEAGE_ERRORS[exc.reason]} {views.TRY_AGAIN}"
        await message.answer(text, reply_markup=edit_keyboard())
        return
    now_day = await today(session, user)
    stored = (await state.get_data()).get("date")
    day = date.fromisoformat(stored) if stored else now_day
    problem = await profiles.check(session, profile, day, value)
    if problem is not None:
        await message.answer(views.violation(problem, day), reply_markup=edit_keyboard())
        return
    reading = await profiles.add_reading(session, profile, day, value, utcnow())
    rows = profiles.as_rules(await profiles.readings_of(session, profile))
    grown = gain(rows, Reading(reading.id, day, value), profile.initial_mileage)
    await state.clear()
    await send_menu(message, session, user, views.reading_saved(value, day, now_day, grown))


# --- history ---


async def _history(
    session: AsyncSession, profile: Profile, page: int, prefix: str = ""
) -> Screen:
    rows = await profiles.readings_of(session, profile)
    pages = max(math.ceil(len(rows) / PAGE_SIZE), 1)
    page = min(max(page, 0), pages - 1)
    chunk = rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    average = monthly_average(profiles.as_rules(rows))
    text = views.mileage_history(profile, chunk, page == pages - 1, average)
    return views.with_header(prefix, text), history_keyboard(chunk, page, pages)


async def _reading(
    callback: CallbackQuery, session: AsyncSession, user: User, reading_id: int
) -> tuple[Profile, OdometerReading] | None:
    profile = await profiles.active_profile(session, user)
    reading = await profiles.get_reading(session, profile, reading_id) if profile else None
    if reading is None:
        await callback.answer(views.STALE_BUTTON)
        return None
    return profile, reading


@router.callback_query(KmCb.filter(F.action == "history"))
async def history(
    callback: CallbackQuery,
    callback_data: KmCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    profile = await profiles.active_profile(session, user)
    if profile is None:
        await callback.answer(views.STALE_BUTTON)
        return
    if await state.get_state() != Km.value.state:
        # Leaving a correction dialog; a new reading may still be typed from the entry screen
        await state.clear()
    await show(callback, *await _history(session, profile, callback_data.page))


@router.callback_query(KmCb.filter(F.action.in_({"open", "edit_value", "edit_date", "delete",
                                                  "delete_yes"})))
async def reading_action(
    callback: CallbackQuery,
    callback_data: KmCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    found = await _reading(callback, session, user, callback_data.id)
    if found is None:
        return
    profile, reading = found
    page = callback_data.page
    action = callback_data.action
    if action == "open":
        await state.clear()
        await show(callback, views.reading_card(reading), reading_keyboard(reading, page))
    elif action == "delete":
        await show(
            callback, views.reading_delete_confirm(reading), reading_delete_keyboard(reading, page)
        )
    elif action == "delete_yes":
        await profiles.delete_reading(session, reading)
        await show(callback, *await _history(session, profile, page, views.READING_DELETED))
    else:
        await state.set_state(Km.edit_value if action == "edit_value" else Km.edit_date)
        await state.set_data({"profile_id": profile.id, "reading_id": reading.id, "page": page})
        prompt = (
            views.reading_edit_value(reading)
            if action == "edit_value"
            else views.reading_edit_date(reading)
        )
        await show(callback, prompt, edit_keyboard())


@router.message(StateFilter(Km.edit_value, Km.edit_date), ANSWER)
async def typed_correction(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    data = await state.get_data()
    profile = await _profile(state, session, user)
    reading = await profiles.get_reading(session, profile, data["reading_id"]) if profile else None
    if reading is None:
        await state.clear()
        await send_menu(message, session, user, views.STALE_BUTTON)
        return
    editing_value = await state.get_state() == Km.edit_value.state
    try:
        if editing_value:
            day, value = reading.date, parse_mileage(message.text)
        else:
            day, value = parse_date(message.text, await today(session, user)), reading.value
    except InvalidInput as exc:
        errors = views.MILEAGE_ERRORS if editing_value else views.DATE_ERRORS
        await message.answer(errors[exc.reason], reply_markup=edit_keyboard())
        return
    problem = await profiles.check(session, profile, day, value, exclude_id=reading.id)
    if problem is not None:
        await message.answer(views.violation(problem, day), reply_markup=edit_keyboard())
        return
    await profiles.update_reading(session, reading, day, value)
    await state.clear()
    text, markup = await _history(session, profile, data["page"], views.reading_updated(reading))
    await message.answer(text, reply_markup=markup)
