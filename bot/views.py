"""All user-facing texts (Telegram HTML)."""

from datetime import date, datetime, timedelta
from html import escape

from bot.db.models import PROFILE_ARCHIVED, Deployment, OdometerReading, Profile, Settings
from bot.services import parse
from bot.services.dates import fmt_date, utc_offset
from bot.services.deployments import STATUS_OK
from bot.services.mileage import Gain, Violation

NBSP = " "

WELCOME = (
    "Это «Автодневник»: история обслуживания машины, пробег, фото и напоминания.\n"
    "Для начала добавим вашу машину."
)
HELP = (
    "<b>Автодневник</b> хранит историю обслуживания машины, пробег, фото "
    "и напоминает о предстоящих работах.\n\n"
    "🚗 Авто — ваши машины: добавить, изменить, выбрать активную, убрать в архив.\n"
    "🛣 Пробег — записать показание одометра, история пробега.\n"
    "⚙️ Настройки — часовой пояс и валюта.\n"
    "Остальные разделы появятся в следующих версиях.\n\n"
    "Команды: /menu — главное меню, /car — машины, /km — пробег, /settings — настройки, "
    "/cancel — отменить текущее действие."
)
CANCELLED = "Отменено."
NOTHING_TO_CANCEL = "Нечего отменять."
SECTION_SOON = "Раздел появится в следующих версиях."
NOT_UNDERSTOOD = "Не понял. Выберите действие в меню или откройте /help."
STALE_BUTTON = "Эта кнопка уже неактуальна."
ERROR = "Что-то пошло не так, попробуйте ещё раз."
NO_CAR = "Машина не выбрана. Добавьте её в разделе 🚗 Авто."
TRY_AGAIN = "Введите число или нажмите «Отмена»."


def km(value: int) -> str:
    """152 300 with a non-breaking space, so the number never wraps."""
    return f"{value:,}".replace(",", NBSP)


def menu_header(profile: Profile | None, mileage: int | None) -> str:
    if profile is None:
        return NO_CAR
    return f"🚗 {escape(profile.name)} · {km(mileage)}{NBSP}км"


def with_header(text: str, header: str) -> str:
    return f"{text}\n\n{header}" if text else header


# --- profile fields ---

FIELD_TITLES = {
    "name": "Название",
    "initial_mileage": "Начальный пробег",
    "make": "Марка",
    "model": "Модель",
    "year": "Год выпуска",
    "plate": "Госномер",
    "vin": "VIN",
    "engine": "Двигатель",
    "purchase_date": "Дата покупки",
    "note": "Заметка",
}

FIELD_PROMPTS = {
    "name": "Как назовём машину? Например, <code>Октавия</code>.",
    "initial_mileage": "Сколько сейчас на одометре, км? Например, <code>152 300</code>.",
    "make": "Марка? Например, <code>Skoda</code>.",
    "model": "Модель? Например, <code>Octavia</code>.",
    "year": "Год выпуска? Например, <code>2019</code>.",
    "plate": "Госномер? Например, <code>А123ВС77</code>.",
    "vin": "VIN — 17 символов с СТС или под лобовым стеклом.",
    "engine": "Двигатель? Выберите или напишите, например <code>1.4 TSI</code>.",
    "purchase_date": "Дата покупки? Формат <code>ДД.ММ.ГГГГ</code>.",
    "note": "Заметка о машине?",
}

ENGINE_CHOICES = ("Бензин", "Дизель", "Гибрид", "Электро", "Газ/бензин")

DATE_ERRORS = {
    parse.FORMAT: "Не понял дату. Формат: <code>ДД.ММ.ГГГГ</code>, <code>ДД.ММ</code>, "
    "«сегодня» или «вчера».",
    parse.FUTURE: "Дата не может быть в будущем.",
    parse.FUTURE_NO_YEAR: "Эта дата в этом году ещё не наступила. Укажите год: "
    "<code>ДД.ММ.ГГГГ</code>.",
    parse.OUT_OF_RANGE: "Слишком давняя дата, проверьте год.",
}
MILEAGE_ERRORS = {
    parse.FORMAT: "Нужно число, например <code>152 300</code>.",
    parse.OUT_OF_RANGE: "Слишком большое число, проверьте пробег.",
}


def field_error(field: str, reason: str, max_length: int | None = None) -> str:
    if field == "initial_mileage":
        return MILEAGE_ERRORS[reason]
    if field == "purchase_date":
        return DATE_ERRORS[reason]
    if field == "year":
        if reason == parse.OUT_OF_RANGE:
            return f"Год должен быть от {parse.MIN_YEAR} до следующего."
        return "Нужен год четырьмя цифрами, например <code>2019</code>."
    if field == "vin":
        return "VIN — это 17 латинских букв и цифр, без I, O и Q."
    if reason == parse.TOO_LONG:
        return f"Слишком длинно: не больше {max_length} символов."
    return "Пустой ответ. Напишите текст или нажмите «Пропустить»."


def name_taken(name: str) -> str:
    return f"Машина «{escape(name)}» уже есть. Придумайте другое название."


def initial_above_readings(lowest: OdometerReading) -> str:
    return (
        f"Начальный пробег не может быть больше показания {km(lowest.value)}{NBSP}км "
        f"от {fmt_date(lowest.date)}."
    )


def field_value(field: str, value) -> str:
    if value is None:
        return "—"
    if field == "initial_mileage":
        return f"{km(value)}{NBSP}км"
    if isinstance(value, date):
        return fmt_date(value)
    return escape(str(value))


def step_prompt(field: str, required: bool, current=None) -> str:
    text = FIELD_PROMPTS[field]
    if not required:
        text += " <i>Необязательно.</i>"
    if current is not None:
        text += f"\nСейчас: {field_value(field, current)}"
    return text


def profile_summary(values: dict) -> str:
    lines = ["Проверьте данные машины:"]
    lines += [
        f"{title}: {field_value(field, values.get(field))}"
        for field, title in FIELD_TITLES.items()
    ]
    return "\n".join(lines)


def profile_card(profile: Profile, mileage: int, is_active: bool, readings: int) -> str:
    head = f"🚗 <b>{escape(profile.name)}</b>"
    if is_active:
        head += " · активная"
    elif profile.status == PROFILE_ARCHIVED:
        head += " · в архиве"
    lines = [head, f"Пробег: {km(mileage)}{NBSP}км"]
    for field in ("make", "model", "year", "plate", "vin", "engine", "purchase_date"):
        value = getattr(profile, field)
        if value is not None:
            lines.append(f"{FIELD_TITLES[field]}: {field_value(field, value)}")
    lines.append(f"Начальный пробег: {field_value('initial_mileage', profile.initial_mileage)}")
    lines.append(f"Показаний пробега: {readings}")
    if profile.note:
        lines.append(f"Заметка: {escape(profile.note)}")
    return "\n".join(lines)


CARS_EMPTY = "Машин пока нет."
CARS_LIST = "Ваши машины. ✅ — активная, с ней работают все разделы."
ARCHIVE_LIST = "Машины в архиве: их данные сохранены, в выборе их нет."
ARCHIVE_EMPTY = "Архив пуст."
CHOOSE_FIELD = "Что изменить?"


def profile_saved(profile: Profile) -> str:
    return f"Сохранено: {escape(profile.name)}, {km(profile.initial_mileage)}{NBSP}км."


def made_active(profile: Profile) -> str:
    return f"Активная машина: {escape(profile.name)}."


def archived(profile: Profile, active: Profile | None) -> str:
    tail = f" Активная машина: {escape(active.name)}." if active else ""
    return f"«{escape(profile.name)}» в архиве.{tail}"


def restored(profile: Profile) -> str:
    return f"«{escape(profile.name)}» снова в списке машин."


def delete_confirm(profile: Profile, readings: int) -> str:
    return (
        f"Удалить «{escape(profile.name)}» вместе со всеми данными "
        f"(показаний пробега: {readings})? Восстановить будет нельзя."
    )


def delete_confirm_again(profile: Profile) -> str:
    return f"Точно удалить «{escape(profile.name)}» навсегда? Это последнее подтверждение."


def deleted(name: str) -> str:
    return f"«{escape(name)}» удалена."


# --- mileage ---

KM_DATE_PROMPT = (
    "За какую дату показание? <code>ДД.ММ.ГГГГ</code> или <code>ДД.ММ</code>, "
    "можно «вчера»."
)


def km_prompt(profile: Profile, mileage: int, day: date | None) -> str:
    when = f" на {fmt_date(day)}" if day else ""
    return (
        f"🚗 {escape(profile.name)} · сейчас {km(mileage)}{NBSP}км\n"
        f"Введите пробег{when}, например <code>{km(mileage)}</code>."
    )


def violation(v: Violation, day: date) -> str:
    if v.bound_date is None:
        reason = f"Пробег не может быть меньше начального ({km(v.bound)}{NBSP}км)."
    elif v.below and v.is_current and day >= v.bound_date:
        reason = f"Пробег не может быть меньше текущего ({km(v.bound)}{NBSP}км)."
    elif v.below:
        reason = (
            f"Пробег на {fmt_date(day)} не может быть меньше {km(v.bound)}{NBSP}км: "
            f"столько было {fmt_date(v.bound_date)}."
        )
    else:
        reason = (
            f"Пробег на {fmt_date(day)} не может быть больше {km(v.bound)}{NBSP}км: "
            f"столько было позже, {fmt_date(v.bound_date)}."
        )
    return f"{reason} {TRY_AGAIN}"


def reading_saved(value: int, day: date, today: date, g: Gain) -> str:
    when = "" if day == today else f", {fmt_date(day)}"
    since = f"с {fmt_date(g.since)}" if g.since else "с начала учёта"
    return f"Сохранено: {km(value)}{NBSP}км{when}. +{km(g.km)}{NBSP}км {since}."


def mileage_history(
    profile: Profile,
    page_rows: list[OdometerReading],
    last_page: bool,
    average: int | None,
) -> str:
    lines = [f"📈 История пробега · {escape(profile.name)}", ""]
    lines += [f"{fmt_date(r.date)} — {km(r.value)}{NBSP}км" for r in page_rows]
    if last_page:
        lines.append(f"Начальный пробег — {km(profile.initial_mileage)}{NBSP}км")
    if not page_rows:
        lines.insert(2, "Показаний пока нет.")
    if average is not None:
        lines += ["", f"В среднем {km(average)}{NBSP}км в месяц."]
    return "\n".join(lines)


def reading_card(r: OdometerReading) -> str:
    return f"Показание: {km(r.value)}{NBSP}км, {fmt_date(r.date)}.\nЧто сделать?"


def reading_edit_value(r: OdometerReading) -> str:
    return f"Новое значение для показания от {fmt_date(r.date)}? Сейчас {km(r.value)}{NBSP}км."


def reading_edit_date(r: OdometerReading) -> str:
    return f"Новая дата для показания {km(r.value)}{NBSP}км? Сейчас {fmt_date(r.date)}."


def reading_delete_confirm(r: OdometerReading) -> str:
    return f"Удалить показание {km(r.value)}{NBSP}км от {fmt_date(r.date)}?"


def reading_updated(r: OdometerReading) -> str:
    return f"Исправлено: {km(r.value)}{NBSP}км, {fmt_date(r.date)}."


READING_DELETED = "Показание удалено."


# --- settings ---

TIMEZONES = (
    ("Калининград", "Europe/Kaliningrad"),
    ("Москва", "Europe/Moscow"),
    ("Самара", "Europe/Samara"),
    ("Екатеринбург", "Asia/Yekaterinburg"),
    ("Омск", "Asia/Omsk"),
    ("Красноярск", "Asia/Krasnoyarsk"),
    ("Иркутск", "Asia/Irkutsk"),
    ("Якутск", "Asia/Yakutsk"),
    ("Владивосток", "Asia/Vladivostok"),
    ("Магадан", "Asia/Magadan"),
    ("Камчатка", "Asia/Kamchatka"),
)
CURRENCIES = ("RUB", "USD", "EUR", "KZT", "BYN")
TZ_PROMPT = (
    "Выберите часовой пояс или пришлите его название, например <code>Asia/Almaty</code>."
)
TZ_UNKNOWN = "Не знаю такого часового пояса. Пример: <code>Asia/Almaty</code>."
CURRENCY_PROMPT = "Выберите валюту или пришлите её код из трёх букв, например <code>GEL</code>."
CURRENCY_BAD = "Нужен код валюты из трёх латинских букв, например <code>GEL</code>."


def tz_title(tz: str, now: datetime) -> str:
    city = next((title for title, name in TIMEZONES if name == tz), None)
    offset = utc_offset(tz, now)
    return f"{city} ({tz}, {offset})" if city else f"{tz} ({offset})"


def settings_text(s: Settings, now: datetime) -> str:
    return (
        "⚙️ Настройки\n"
        f"Часовой пояс: {escape(tz_title(s.timezone, now))}\n"
        f"Валюта: {s.currency}"
    )


SAVED = "Сохранено."


# --- service ---


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
