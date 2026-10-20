from datetime import datetime

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import views
from bot.clock import utcnow
from bot.keyboards import main_menu

router = Router(name="start")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(views.WELCOME, reply_markup=main_menu())


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(views.MENU, reply_markup=main_menu())


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer(views.HELP, reply_markup=main_menu())


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    # No state filter: /cancel must work on any step of any dialog
    text = views.CANCELLED if await state.get_state() is not None else views.NOTHING_TO_CANCEL
    await state.clear()
    await message.answer(text, reply_markup=main_menu())


@router.message(Command("status"))
async def status(
    message: Message, started_at: datetime, app_version: str | None = None
) -> None:
    await message.answer(views.status_text(app_version, utcnow() - started_at))
