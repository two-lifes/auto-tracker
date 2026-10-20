from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup

from bot.db.models import PROFILE_ACTIVE, Profile
from bot.keyboards.common import button, inline, pairs


class CarCb(CallbackData, prefix="car"):
    # list, new, archive_list, open, activate, edit, archive, restore, delete, delete2
    action: str
    id: int = 0


def cars_keyboard(
    profiles: list[Profile], active_id: int | None, archived: int
) -> InlineKeyboardMarkup:
    cars = [
        button(("✅ " if p.id == active_id else "") + p.name, CarCb(action="open", id=p.id))
        for p in profiles
    ]
    tail = [button("➕ Добавить авто", CarCb(action="new"))]
    if archived:
        tail.append(button(f"Архив ({archived})", CarCb(action="archive_list")))
    return inline(*pairs(cars), tail)


def card_keyboard(
    profile: Profile, is_active: bool, with_list: bool, archived: int = 0
) -> InlineKeyboardMarkup:
    """``with_list``: there are several cars, so the card leads back to their list."""
    if profile.status != PROFILE_ACTIVE:
        return inline(
            [
                button("Восстановить", CarCb(action="restore", id=profile.id)),
                button("Удалить", CarCb(action="delete", id=profile.id)),
            ],
            [button("‹ Архив", CarCb(action="archive_list"))],
        )
    first = []
    if not is_active:
        first.append(button("Сделать активной", CarCb(action="activate", id=profile.id)))
    actions = [
        button("Изменить", CarCb(action="edit", id=profile.id)),
        button("В архив", CarCb(action="archive", id=profile.id)),
    ]
    if with_list:
        tail = [button("‹ Все машины", CarCb(action="list"))]
    else:
        tail = [button("➕ Добавить авто", CarCb(action="new"))]
        if archived:
            tail.append(button(f"Архив ({archived})", CarCb(action="archive_list")))
    return inline(first, actions, tail)


def archive_keyboard(profiles: list[Profile]) -> InlineKeyboardMarkup:
    return inline(
        *pairs([button(p.name, CarCb(action="open", id=p.id)) for p in profiles]),
        [button("‹ Все машины", CarCb(action="list"))],
    )


def delete_keyboard(profile: Profile, final: bool) -> InlineKeyboardMarkup:
    yes = (
        button("Да, удалить навсегда", CarCb(action="delete2", id=profile.id))
        if final
        else button("Удалить", CarCb(action="delete_ask2", id=profile.id))
    )
    return inline([yes, button("Отмена", CarCb(action="open", id=profile.id))])
