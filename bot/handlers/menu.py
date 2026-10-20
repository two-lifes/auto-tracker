from aiogram import F, Router
from aiogram.types import Message

from bot import views
from bot.keyboards import MENU_HISTORY, MENU_PHOTOS, MENU_RECORD, MENU_REMINDERS, main_menu

router = Router(name="menu")


# Sections of later stages; each gets its own router when its stage comes
@router.message(F.text.in_({MENU_RECORD, MENU_HISTORY, MENU_REMINDERS, MENU_PHOTOS}))
async def section_soon(message: Message) -> None:
    await message.answer(views.SECTION_SOON, reply_markup=main_menu())
