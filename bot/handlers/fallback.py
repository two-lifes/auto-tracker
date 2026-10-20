from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot import views
from bot.keyboards import main_menu

router = Router(name="fallback")


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    # Buttons from finished or abandoned dialogs; answer so Telegram stops the spinner
    await callback.answer(views.STALE_BUTTON)


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer(views.NOT_UNDERSTOOD, reply_markup=main_menu())
