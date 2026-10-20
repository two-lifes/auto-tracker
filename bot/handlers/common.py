from datetime import date

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import views
from bot.clock import utcnow
from bot.db.models import User
from bot.db.repo import get_settings
from bot.keyboards import MENU_BUTTONS, main_menu
from bot.services import profiles
from bot.services.dates import local_today

# Free-text answers to a dialog step. Commands and menu buttons are never an answer:
# they leave the dialog, whatever step it is on.
ANSWER = F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_BUTTONS)


async def today(session: AsyncSession, user: User) -> date:
    return local_today(utcnow(), (await get_settings(session, user)).timezone)


async def header(session: AsyncSession, user: User) -> str:
    profile = await profiles.active_profile(session, user)
    mileage = await profiles.current_of(session, profile) if profile else None
    return views.menu_header(profile, mileage)


async def send_menu(
    message: Message | InaccessibleMessage, session: AsyncSession, user: User, text: str = ""
) -> None:
    """``text`` followed by the «🚗 car · mileage» line, with the main menu keyboard."""
    await message.answer(
        views.with_header(text, await header(session, user)), reply_markup=main_menu()
    )


async def show(
    callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Replaces the tapped message with ``text``; sends a new one if it can't be edited.

    Telegram may hand over an InaccessibleMessage (old or deleted), which has no edit methods.
    """
    await callback.answer()
    if not isinstance(callback.message, Message):
        await callback.message.answer(text, reply_markup=markup)
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        # Re-rendering identical content (e.g. a double tap) is a harmless no-op
        if "message is not modified" not in str(exc):
            raise

