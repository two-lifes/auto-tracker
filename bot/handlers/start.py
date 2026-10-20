from datetime import datetime

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import views
from bot.clock import utcnow
from bot.db.models import User
from bot.handlers.common import send_menu, show
from bot.handlers.profile_form import start_create
from bot.keyboards.common import CancelCb
from bot.services import profiles

router = Router(name="start")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    if not await profiles.has_any(session, user):
        # First launch (FR-2.6): nothing works without a car
        await start_create(message, state, views.WELCOME)
        return
    await send_menu(message, session, user)


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    await send_menu(message, session, user)


@router.message(Command("help"))
async def help_(message: Message, session: AsyncSession, user: User) -> None:
    await send_menu(message, session, user, views.HELP)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    # No state filter: /cancel must work on any step of any dialog
    text = views.CANCELLED if await state.get_state() is not None else views.NOTHING_TO_CANCEL
    await state.clear()
    await send_menu(message, session, user, text)


@router.callback_query(CancelCb.filter())
async def cancel_button(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await state.clear()
    await show(callback, views.CANCELLED)
    await send_menu(callback.message, session, user)


@router.message(Command("status"))
async def status(
    message: Message, started_at: datetime, app_version: str | None = None
) -> None:
    await message.answer(views.status_text(app_version, utcnow() - started_at))
