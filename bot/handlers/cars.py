"""🚗 Авто: list, card, switching, archive and deletion of car profiles (FR-2)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import views
from bot.clock import utcnow
from bot.db.models import PROFILE_ACTIVE, PROFILE_ARCHIVED, User
from bot.handlers.common import send_menu, show
from bot.handlers.profile_form import start_create, start_edit
from bot.handlers.screens import archive_screen, card_screen, cars_screen
from bot.keyboards import MENU_CARS
from bot.keyboards.cars import CarCb, delete_keyboard
from bot.services import profiles

router = Router(name="cars")


@router.message(Command("car"))
@router.message(F.text == MENU_CARS)
async def cars(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    text, markup = await cars_screen(session, user)
    await message.answer(text, reply_markup=markup)


@router.callback_query(CarCb.filter(F.action == "list"))
async def cars_list(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    await show(callback, *await cars_screen(session, user))


@router.callback_query(CarCb.filter(F.action == "archive_list"))
async def archive_list(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    await show(callback, *await archive_screen(session, user))


@router.callback_query(CarCb.filter(F.action == "new"))
async def new_car(callback: CallbackQuery, state: FSMContext) -> None:
    await start_create(callback, state)


# list, archive_list and new are handled above
@router.callback_query(CarCb.filter())
async def car_action(
    callback: CallbackQuery,
    callback_data: CarCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    profile = await profiles.get_profile(session, user, callback_data.id)
    if profile is None:
        await callback.answer(views.STALE_BUTTON)
        return
    action = callback_data.action
    is_active = profile.status == PROFILE_ACTIVE
    now = utcnow()
    if action == "open":
        await state.clear()
        await show(callback, *await card_screen(session, user, profile))
    elif action == "activate" and is_active:
        await profiles.set_active(session, user, profile)
        await show(callback, *await card_screen(session, user, profile))
        await send_menu(callback.message, session, user, views.made_active(profile))
    elif action == "edit" and is_active:
        await start_edit(callback, state, profile)
    elif action == "archive" and is_active:
        await profiles.archive(session, user, profile, now)
        active = await profiles.active_profile(session, user)
        await show(callback, *await cars_screen(session, user, views.archived(profile, active)))
        await send_menu(callback.message, session, user)
    elif action == "restore" and profile.status == PROFILE_ARCHIVED:
        await profiles.restore(session, user, profile, now)
        await show(callback, *await cars_screen(session, user, views.restored(profile)))
    elif action == "delete" and profile.status == PROFILE_ARCHIVED:
        count = await profiles.count_readings(session, profile)
        await show(callback, views.delete_confirm(profile, count), delete_keyboard(profile, False))
    elif action == "delete_ask2" and profile.status == PROFILE_ARCHIVED:
        await show(callback, views.delete_confirm_again(profile), delete_keyboard(profile, True))
    elif action == "delete2" and profile.status == PROFILE_ARCHIVED:
        name = profile.name
        await profiles.delete(session, user, profile)
        await show(callback, *await archive_screen(session, user, views.deleted(name)))
    else:
        await callback.answer(views.STALE_BUTTON)
