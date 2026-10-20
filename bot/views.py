"""All user-facing texts (Telegram HTML)."""

from datetime import timedelta
from html import escape

from bot.db.models import Deployment
from bot.services.deployments import STATUS_OK

WELCOME = (
    "Это «Автодневник»: история обслуживания машины, пробег, фото и напоминания.\n"
    "Разделы появятся в следующих версиях, пока доступны /help и /cancel."
)
MENU = "Главное меню."
HELP = (
    "<b>Автодневник</b> хранит историю обслуживания машины, пробег, фото "
    "и напоминает о предстоящих работах.\n\n"
    "Команды:\n"
    "/menu — главное меню\n"
    "/help — эта справка\n"
    "/cancel — отменить текущее действие\n\n"
    "Разделы меню пока в разработке."
)
CANCELLED = "Отменено."
NOTHING_TO_CANCEL = "Нечего отменять."
SECTION_SOON = "Раздел появится в следующих версиях."
NOT_UNDERSTOOD = "Не понял. Выберите действие в меню или откройте /help."
STALE_BUTTON = "Эта кнопка уже неактуальна."
ERROR = "Что-то пошло не так, попробуйте ещё раз."


def format_duration(value: timedelta) -> str:
    minutes = max(int(value.total_seconds()) // 60, 0)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days} д {hours} ч"
    if hours:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"


def status_text(version: str | None, uptime: timedelta) -> str:
    shown = f"<code>{escape(version[:7])}</code>" if version else "локальная"
    return (
        f"Версия: {shown}\n"
        f"Работает: {format_duration(uptime)}\n"
        # Backups arrive in stage 4
        "Последний бэкап: нет данных"
    )


def deployment_text(d: Deployment) -> str:
    if d.status == STATUS_OK:
        title = f"\n{escape(d.title)}" if d.title else ""
        return f"🔄 Бот обновлён до версии <code>{d.version[:7]}</code>{title}"
    return (
        f"⚠️ Обновление <code>{d.version[:7]}</code> не запустилось.\n"
        "Бот вернулся на предыдущую версию."
    )
