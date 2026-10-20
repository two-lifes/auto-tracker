from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.common import button, cancel_button, inline, pairs
from bot.views import CURRENCIES, TIMEZONES


class SetCb(CallbackData, prefix="set"):
    # tz, tz_pick (arg: zone), currency, currency_pick (arg: code)
    action: str
    arg: str = ""


def settings_keyboard() -> InlineKeyboardMarkup:
    return inline(
        [
            button("🕒 Часовой пояс", SetCb(action="tz")),
            button("💱 Валюта", SetCb(action="currency")),
        ]
    )


def tz_keyboard() -> InlineKeyboardMarkup:
    return inline(
        *pairs([button(title, SetCb(action="tz_pick", arg=tz)) for title, tz in TIMEZONES]),
        [cancel_button()],
    )


def currency_keyboard() -> InlineKeyboardMarkup:
    return inline(
        [button(code, SetCb(action="currency_pick", arg=code)) for code in CURRENCIES],
        [cancel_button()],
    )
