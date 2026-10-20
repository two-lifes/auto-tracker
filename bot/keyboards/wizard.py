from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.common import button, cancel_button, inline, pairs


class WizardCb(CallbackData, prefix="wz"):
    # skip, back, pick (arg: choice index), clear, save, edit, summary, field (arg: field)
    action: str
    arg: str = ""
    # The field the button was shown for: a button left on an earlier step's message must
    # not act on the current step
    step: str = ""


def step_keyboard(
    field: str, choices: tuple[str, ...], required: bool, can_go_back: bool, single: bool
) -> InlineKeyboardMarkup:
    """``single``: editing one field, so «Пропустить» would mean nothing; «Очистить» instead."""
    picks = pairs(
        [button(c, WizardCb(action="pick", arg=str(i), step=field)) for i, c in enumerate(choices)]
    )
    nav = []
    if not required:
        nav.append(
            button("Очистить", WizardCb(action="clear", step=field))
            if single
            else button("Пропустить", WizardCb(action="skip", step=field))
        )
    if can_go_back:
        nav.append(button("‹ Назад", WizardCb(action="back", step=field)))
    nav.append(cancel_button())
    return inline(*picks, nav)


def summary_keyboard() -> InlineKeyboardMarkup:
    return inline(
        [button("Сохранить", WizardCb(action="save")), button("Изменить", WizardCb(action="edit"))],
        [cancel_button()],
    )


def fields_keyboard(fields: dict[str, str], back: CallbackData) -> InlineKeyboardMarkup:
    return inline(
        *pairs([button(title, WizardCb(action="field", arg=f)) for f, title in fields.items()]),
        [button("‹ Назад", back)],
    )
