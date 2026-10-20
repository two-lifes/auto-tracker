"""Creating a car profile step by step (D-12) and editing one field of it (FR-2.1, FR-2.2).

FSM data: ``mode`` (create / edit), ``i`` (index of the current field), ``values`` (entered
so far, JSON-safe), ``single`` (one field is being edited, then back to the summary or the
card), ``profile_id`` (edit mode). All of it lives in the DB, so a restart loses nothing.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import views
from bot.clock import utcnow
from bot.db.models import Profile, User
from bot.handlers.common import ANSWER, send_menu, show, today
from bot.handlers.screens import card_screen
from bot.keyboards.cars import CarCb
from bot.keyboards.wizard import WizardCb, fields_keyboard, step_keyboard, summary_keyboard
from bot.services import parse, profiles
from bot.services.parse import InvalidInput

router = Router(name="profile_form")


class ProfileForm(StatesGroup):
    step = State()
    summary = State()


@dataclass(frozen=True)
class Field:
    key: str
    parse: Callable[[str, date], Any]
    required: bool = False
    max_length: int | None = None
    choices: tuple[str, ...] = ()


def _text(max_length: int) -> Callable[[str, date], str]:
    return lambda text, _today: parse.parse_text(text, max_length)


FIELDS = (
    Field("name", _text(64), required=True, max_length=64),
    Field("initial_mileage", lambda t, _: parse.parse_mileage(t), required=True),
    Field("make", _text(64), max_length=64),
    Field("model", _text(64), max_length=64),
    Field("year", parse.parse_year),
    Field("plate", lambda t, _: parse.parse_plate(t), max_length=16),
    Field("vin", lambda t, _: parse.parse_vin(t)),
    Field("engine", _text(64), max_length=64, choices=views.ENGINE_CHOICES),
    Field("purchase_date", parse.parse_date),
    Field("note", _text(1000), max_length=1000),
)
INDEX = {f.key: i for i, f in enumerate(FIELDS)}


def _to_json(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def _from_json(key: str, value: Any) -> Any:
    return date.fromisoformat(value) if key == "purchase_date" and value else value


def _decoded(values: dict) -> dict:
    return {k: _from_json(k, v) for k, v in values.items()}


Target = Message | CallbackQuery


async def _reply(target: Target, text: str, markup) -> None:
    if isinstance(target, CallbackQuery):
        await show(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


async def _ask(target: Target, state: FSMContext, error: str = "") -> None:
    data = await state.get_data()
    field = FIELDS[data["i"]]
    single = data.get("single", False)
    current = _from_json(field.key, data["values"].get(field.key)) if single else None
    text = views.step_prompt(field.key, field.required, current)
    await state.set_state(ProfileForm.step)
    await _reply(
        target,
        f"{error}\n\n{text}" if error else text,
        step_keyboard(
            field.key, field.choices, field.required,
            can_go_back=single or data["i"] > 0, single=single,
        ),
    )


async def _summary(target: Target, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(ProfileForm.summary)
    await _reply(target, views.profile_summary(_decoded(data["values"])), summary_keyboard())


async def start_create(target: Target, state: FSMContext, intro: str = "") -> None:
    await state.set_data({"mode": "create", "i": 0, "values": {}})
    await state.set_state(ProfileForm.step)
    if intro:
        await (target.message if isinstance(target, CallbackQuery) else target).answer(intro)
    await _ask(target, state)


async def start_edit(callback: CallbackQuery, state: FSMContext, profile: Profile) -> None:
    values = {k: _to_json(getattr(profile, k)) for k in profiles.EDITABLE_FIELDS}
    await state.set_data({"mode": "edit", "profile_id": profile.id, "values": values})
    await _choose_field(callback, state, CarCb(action="open", id=profile.id))


async def _choose_field(callback: CallbackQuery, state: FSMContext, back_to) -> None:
    """In edit mode the summary state means «picking a field»."""
    await state.set_state(ProfileForm.summary)
    await show(callback, views.CHOOSE_FIELD, fields_keyboard(views.FIELD_TITLES, back_to))


async def _check_value(
    session: AsyncSession, user: User, data: dict, key: str, value: Any
) -> str | None:
    """Rules that need the DB; None when the value is fine."""
    profile_id = data.get("profile_id")
    if key == "name" and await profiles.name_taken(session, user, value, profile_id):
        return views.name_taken(value)
    if key == "initial_mileage" and profile_id is not None:
        profile = await profiles.get_profile(session, user, profile_id)
        rows = await profiles.readings_of(session, profile) if profile else []
        lowest = min(rows, key=lambda r: r.value, default=None)
        if lowest is not None and value > lowest.value:
            return views.initial_above_readings(lowest)
    return None


async def _accept(
    target: Target, state: FSMContext, session: AsyncSession, user: User, value: Any
) -> None:
    data = await state.get_data()
    field = FIELDS[data["i"]]
    if value is not None:
        error = await _check_value(session, user, data, field.key, value)
        if error:
            await _ask(target, state, error)
            return
    data["values"][field.key] = _to_json(value)
    await state.update_data(values=data["values"])
    if data["mode"] == "edit":
        await _save_field(target, state, session, user, field.key, value)
    elif data.get("single") or data["i"] + 1 == len(FIELDS):
        await state.update_data(single=False)
        await _summary(target, state)
    else:
        await state.update_data(i=data["i"] + 1)
        await _ask(target, state)


async def _save_field(
    target: Target, state: FSMContext, session: AsyncSession, user: User, key: str, value: Any
) -> None:
    profile = await profiles.get_profile(session, user, (await state.get_data())["profile_id"])
    await state.clear()
    if profile is None:
        await _reply(target, views.STALE_BUTTON, None)
        return
    await profiles.update_field(session, profile, key, value, utcnow())
    text, markup = await card_screen(session, user, profile, views.SAVED)
    await _reply(target, text, markup)


@router.message(StateFilter(ProfileForm.step), ANSWER)
async def typed(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    data = await state.get_data()
    field = FIELDS[data["i"]]
    try:
        value = field.parse(message.text, await today(session, user))
    except InvalidInput as exc:
        await _ask(message, state, views.field_error(field.key, exc.reason, field.max_length))
        return
    await _accept(message, state, session, user, value)


async def _current_step(callback: CallbackQuery, state: FSMContext, cb: WizardCb) -> bool:
    data = await state.get_data()
    if await state.get_state() != ProfileForm.step.state or FIELDS[data["i"]].key != cb.step:
        await callback.answer(views.STALE_BUTTON)
        return False
    return True


@router.callback_query(WizardCb.filter(F.action.in_({"skip", "clear", "pick"})))
async def step_button(
    callback: CallbackQuery,
    callback_data: WizardCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    if not await _current_step(callback, state, callback_data):
        return
    field = FIELDS[(await state.get_data())["i"]]
    if callback_data.action == "pick":
        value = field.choices[int(callback_data.arg)]
    elif field.required:
        await callback.answer(views.STALE_BUTTON)
        return
    else:
        value = None
    await _accept(callback, state, session, user, value)


@router.callback_query(WizardCb.filter(F.action == "back"))
async def back(
    callback: CallbackQuery,
    callback_data: WizardCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    if not await _current_step(callback, state, callback_data):
        return
    data = await state.get_data()
    if data["mode"] == "edit":
        await _choose_field(callback, state, CarCb(action="open", id=data["profile_id"]))
    elif data.get("single"):
        await state.update_data(single=False)
        await _summary(callback, state)
    else:
        await state.update_data(i=data["i"] - 1)
        await _ask(callback, state)


@router.callback_query(WizardCb.filter(F.action.in_({"save", "edit", "summary", "field"})))
async def summary_button(
    callback: CallbackQuery,
    callback_data: WizardCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    if await state.get_state() != ProfileForm.summary.state:
        await callback.answer(views.STALE_BUTTON)
        return
    data = await state.get_data()
    action = callback_data.action
    if action == "field" and callback_data.arg in INDEX:
        await state.update_data(i=INDEX[callback_data.arg], single=True)
        await _ask(callback, state)
    elif action == "edit" and data["mode"] == "create":
        await _choose_field(callback, state, WizardCb(action="summary"))
    elif action == "summary" and data["mode"] == "create":
        await _summary(callback, state)
    elif action == "save" and data["mode"] == "create":
        await _create(callback, state, session, user, data)
    else:
        await callback.answer(views.STALE_BUTTON)


async def _create(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, data: dict
) -> None:
    values = _decoded(data["values"])
    # The name could have been taken while this dialog was waiting
    if await profiles.name_taken(session, user, values["name"]):
        await state.update_data(i=INDEX["name"], single=True)
        await _ask(callback, state, views.name_taken(values["name"]))
        return
    profile = await profiles.create_profile(session, user, values, utcnow())
    await state.clear()
    await show(callback, views.profile_saved(profile))
    await send_menu(callback.message, session, user, views.made_active(profile))
