from aiogram import F, Router
from aiogram.types import Message

from bot import views
from bot.keyboards import MENU_BUTTONS, main_menu

router = Router(name="menu")


# Stage 0 placeholder: each section gets its own router in later stages
@router.message(F.text.in_(MENU_BUTTONS))
async def section_soon(message: Message) -> None:
    await message.answer(views.SECTION_SOON, reply_markup=main_menu())
