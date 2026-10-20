from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup

from bot.db.models import OdometerReading
from bot.keyboards.common import button, cancel_button, inline, pairs


class KmCb(CallbackData, prefix="km"):
    # other_date, day (arg: today / yesterday), history (page), open (id), edit_value,
    # edit_date, delete, delete_yes
    action: str
    id: int = 0
    page: int = 0
    arg: str = ""


def entry_keyboard() -> InlineKeyboardMarkup:
    return inline(
        [
            button("📅 Другая дата", KmCb(action="other_date")),
            button("📈 История", KmCb(action="history")),
        ],
        [cancel_button()],
    )


def date_keyboard() -> InlineKeyboardMarkup:
    return inline(
        [
            button("Сегодня", KmCb(action="day", arg="today")),
            button("Вчера", KmCb(action="day", arg="yesterday")),
        ],
        [cancel_button()],
    )


def history_keyboard(
    rows: list[OdometerReading], page: int, pages: int
) -> InlineKeyboardMarkup:
    readings = [
        button(f"{r.date:%d.%m.%y} · {r.value:,}".replace(",", " "), KmCb(action="open", id=r.id))
        for r in rows
    ]
    nav = []
    if pages > 1:
        if page > 0:
            nav.append(button("‹", KmCb(action="history", page=page - 1)))
        nav.append(button(f"{page + 1}/{pages}", KmCb(action="history", page=page)))
        if page < pages - 1:
            nav.append(button("›", KmCb(action="history", page=page + 1)))
    return inline(*pairs(readings), nav)


def reading_keyboard(r: OdometerReading, page: int) -> InlineKeyboardMarkup:
    return inline(
        [
            button("Изменить пробег", KmCb(action="edit_value", id=r.id, page=page)),
            button("Изменить дату", KmCb(action="edit_date", id=r.id, page=page)),
        ],
        [
            button("Удалить", KmCb(action="delete", id=r.id, page=page)),
            button("‹ История", KmCb(action="history", page=page)),
        ],
    )


def reading_delete_keyboard(r: OdometerReading, page: int) -> InlineKeyboardMarkup:
    return inline(
        [
            button("Да, удалить", KmCb(action="delete_yes", id=r.id, page=page)),
            button("Отмена", KmCb(action="open", id=r.id, page=page)),
        ]
    )


def edit_keyboard() -> InlineKeyboardMarkup:
    return inline([cancel_button()])
