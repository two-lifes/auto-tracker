from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

# Main menu buttons from docs/05-bot-ux.md, in display order
MENU_RECORD = "➕ Запись"
MENU_MILEAGE = "🛣 Пробег"
MENU_HISTORY = "📜 История"
MENU_REMINDERS = "🔔 Напоминания"
MENU_PHOTOS = "📷 Фото"
MENU_CARS = "🚗 Авто"
MENU_SETTINGS = "⚙️ Настройки"

MENU_BUTTONS = (
    MENU_RECORD,
    MENU_MILEAGE,
    MENU_HISTORY,
    MENU_REMINDERS,
    MENU_PHOTOS,
    MENU_CARS,
    MENU_SETTINGS,
)


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [MENU_RECORD, MENU_MILEAGE],
        [MENU_HISTORY, MENU_REMINDERS],
        [MENU_PHOTOS, MENU_CARS],
        [MENU_SETTINGS],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
    )
