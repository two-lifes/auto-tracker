"""Stage 1 dialogs: US-1 (first car), US-2 (second car), US-3 (mileage), settings, restarts."""

from datetime import UTC, date, datetime

from sqlalchemy import select

from bot import views
from bot.db.models import FsmState, OdometerReading, Profile, Settings, User
from bot.db.session import create_engine, create_sessionmaker
from tests.harness import add_car

TODAY = date(2026, 10, 17)  # conftest NOW in Moscow


async def _profiles(h) -> list[tuple[str, str]]:
    return [(p.name, p.status) for p in await h.all(Profile)]


async def _dialogs(h) -> list[FsmState]:
    async with h.sessionmaker() as session:
        return list(await session.scalars(select(FsmState)))


async def _settings(h) -> Settings:
    async with h.sessionmaker() as session:
        return (await session.scalars(select(Settings))).one()


async def _active_name(h) -> str | None:
    user = (await h.all(User))[0]
    profiles = {p.id: p.name for p in await h.all(Profile)}
    return profiles.get(user.active_profile_id)


# --- US-1: first launch ---


async def test_first_start_creates_car(h):
    await h.text("/start")
    assert "Как назовём машину" in h.last_plain()
    assert "Пропустить" not in h.buttons()  # the name is required
    await h.text("Октавия")
    assert "одометре" in h.last_plain()
    await h.text("152 300")
    assert "Марка" in h.last_plain()
    while "Пропустить" in h.buttons():
        await h.press("Пропустить")
    assert "Проверьте данные машины" in h.last_plain()
    assert "Начальный пробег: 152 300 км" in h.last_plain()
    await h.press("Сохранить")
    assert h.last_plain().endswith("🚗 Октавия · 152 300 км")
    assert await _profiles(h) == [("Октавия", "active")]
    assert await _active_name(h) == "Октавия"
    assert await _dialogs(h) == []  # the finished dialog leaves nothing behind


async def test_optional_fields_are_saved(h):
    await h.text("/start")
    await h.text("Октавия")
    await h.text("152300")
    for answer in ("Skoda", "Octavia", "2019", "а123вс77", "TMBJG7NE5J0123456"):
        await h.text(answer)
    await h.press("Бензин")
    await h.text("01.06.2021")
    await h.text("Купил у дилера")
    await h.press("Сохранить")
    p = (await h.all(Profile))[0]
    assert (p.make, p.model, p.year, p.plate, p.vin, p.engine) == (
        "Skoda", "Octavia", 2019, "А123ВС77", "TMBJG7NE5J0123456", "Бензин"
    )
    assert (p.purchase_date, p.note, p.initial_mileage) == (date(2021, 6, 1), "Купил у дилера",
                                                             152_300)


async def test_wrong_input_repeats_question(h):
    await h.text("/start")
    await h.text("Октавия")
    reply = await h.text("много")
    assert "Нужно число" in reply and "одометре" in reply
    await h.text("152 300")
    for _ in range(2):
        await h.press("Пропустить")
    reply = await h.text("1800")
    assert "Год должен быть" in reply and "Год выпуска" in reply
    assert "Пропустить" in h.buttons()


async def test_future_purchase_date_without_year_asks_for_year(h):
    await h.text("/start")
    await h.text("Октавия")
    await h.text("100000")
    while "Дата покупки" not in h.last_plain():
        await h.press("Пропустить")
    reply = await h.text("25.12")
    assert "ещё не наступила" in reply


async def test_back_returns_to_previous_step(h):
    await h.text("/start")
    await h.text("Октавия")
    await h.text("152 300")
    await h.text("Skoda")
    await h.press("‹ Назад")
    assert "Марка" in h.last_plain()
    await h.press("‹ Назад")
    assert "одометре" in h.last_plain()
    await h.text("150 000")
    assert "Модель" in await h.text("Skoda")
    while "Пропустить" in h.buttons():
        await h.press("Пропустить")
    assert "Марка: Skoda" in h.last_plain()
    assert "Начальный пробег: 150 000 км" in h.last_plain()


async def test_cancel_on_any_step(h):
    await h.text("/start")
    await h.text("Октавия")
    await h.press("Отмена")
    assert await h.all(Profile) == []
    assert h.last_plain().startswith(views.NO_CAR)
    assert await _dialogs(h) == []


async def test_old_step_button_does_not_act(h):
    await h.text("/start")
    await h.text("Октавия")
    await h.text("152 300")
    skip_make = h.buttons()["Пропустить"]
    await h.text("Skoda")  # now on «Модель»
    await h.tap(skip_make)
    assert h.net.callback_answers()[-1] == views.STALE_BUTTON
    assert "Модель" in h.last_plain()


async def test_summary_edit_field(h):
    await h.text("/start")
    await h.text("Октавия")
    await h.text("152 300")
    while "Пропустить" in h.buttons():
        await h.press("Пропустить")
    await h.press("Изменить")
    await h.press("Модель")
    await h.text("Octavia")
    assert "Модель: Octavia" in h.last_plain()
    await h.press("Сохранить")
    assert (await h.all(Profile))[0].model == "Octavia"


async def test_menu_button_leaves_dialog(h):
    await h.text("/start")
    await h.text("Октавия")
    await h.text("⚙️ Настройки")
    assert "Настройки" in h.last_plain()
    assert await _dialogs(h) == []


async def test_restart_mid_dialog_keeps_answers(h, tmp_path):
    await h.text("/start")
    await h.text("Октавия")
    await h.text("152 300")
    # A new process: fresh engine and storage on the same DB file
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    h.sessionmaker = create_sessionmaker(engine)
    h.dp.fsm.storage.sessionmaker = h.sessionmaker
    try:
        assert "Модель" in await h.text("Skoda")  # continued from «Марка»
        while "Пропустить" in h.buttons():
            await h.press("Пропустить")
        await h.press("Сохранить")
        p = (await h.all(Profile))[0]
        assert (p.name, p.initial_mileage, p.make) == ("Октавия", 152_300, "Skoda")
    finally:
        await engine.dispose()


# --- US-2: second car ---


async def test_second_car_switcher_and_isolation(h):
    await add_car(h)
    await h.text("/km")
    await h.text("153 000")
    # One car: 🚗 Авто shows its card, nothing to switch
    await h.text("/car")
    assert "Сделать активной" not in h.buttons()
    assert "‹ Все машины" not in h.buttons()

    await add_car(h, "Рапид", "40 000", first=False)
    assert await _active_name(h) == "Рапид"  # the new car is the one to work with
    assert h.last_plain().endswith("🚗 Рапид · 40 000 км")

    await h.text("/car")
    assert set(h.buttons()) >= {"✅ Рапид", "Октавия"}
    await h.press("Октавия")
    assert "Октавия" in h.last_plain() and "Пробег: 153 000 км" in h.last_plain()
    await h.press("Сделать активной")
    assert await _active_name(h) == "Октавия"
    assert h.last_plain().endswith("🚗 Октавия · 153 000 км")

    # The second car's mileage knows nothing about the first one's readings
    rapid = next(p for p in await h.all(Profile) if p.name == "Рапид")
    readings = await h.all(OdometerReading)
    assert all(r.profile_id != rapid.id for r in readings)


async def test_car_names_are_unique_ignoring_case(h):
    await add_car(h)
    await h.text("/car")
    await h.press("➕ Добавить авто")
    reply = await h.text("октавия")
    assert "уже есть" in reply
    assert len(await h.all(Profile)) == 1


async def test_archive_restore_and_delete(h):
    await add_car(h)
    await add_car(h, "Рапид", "40 000", first=False)
    await h.text("/km")
    await h.text("41 000")
    await h.text("/car")
    await h.press("✅ Рапид")
    await h.press("В архив")
    assert await _profiles(h) == [("Октавия", "active"), ("Рапид", "archived")]
    assert await _active_name(h) == "Октавия"

    await h.text("/car")
    await h.press("Архив (1)")
    await h.press("Рапид")
    await h.press("Восстановить")
    assert await _profiles(h) == [("Октавия", "active"), ("Рапид", "active")]

    await h.text("/car")
    await h.press("Рапид")
    await h.press("В архив")
    await h.text("/car")
    await h.press("Архив (1)")
    await h.press("Рапид")
    await h.press("Удалить")
    assert "Восстановить будет нельзя" in h.last_plain()
    await h.press("Удалить")
    assert "последнее подтверждение" in h.last_plain()
    await h.press("Да, удалить навсегда")
    assert await _profiles(h) == [("Октавия", "active")]
    assert await h.all(OdometerReading) == []  # its readings went with it


async def test_archiving_the_only_car(h):
    await add_car(h)
    await h.text("/car")
    await h.press("В архив")
    assert await _active_name(h) is None
    assert h.last_plain().startswith(views.NO_CAR)
    assert (await h.text("/km")) == views.NO_CAR


async def test_edit_profile_field(h):
    await add_car(h)
    await h.text("/car")
    await h.press("Изменить")
    await h.press("Год выпуска")
    reply = await h.text("2019")
    assert reply.startswith(views.SAVED) and "Год выпуска: 2019" in reply
    await h.press("Изменить")
    await h.press("Год выпуска")
    await h.press("Очистить")
    assert (await h.all(Profile))[0].year is None


async def test_initial_mileage_cannot_exceed_readings(h):
    await add_car(h, mileage="100 000")
    await h.text("/km")
    await h.text("110 000")
    await h.text("/car")
    await h.press("Изменить")
    await h.press("Начальный пробег")
    reply = await h.text("120 000")
    assert "не может быть больше показания 110 000 км" in reply
    await h.text("90 000")
    assert (await h.all(Profile))[0].initial_mileage == 90_000


async def test_foreign_or_deleted_car_button_is_stale(h):
    await add_car(h)
    await h.tap("car:open:999")
    assert h.net.callback_answers()[-1] == views.STALE_BUTTON


# --- US-3: mileage ---


async def test_mileage_saved_with_gain(h):
    await add_car(h)
    await h.text("🛣 Пробег")
    reply = await h.text("153 500")
    assert reply.startswith("Сохранено: 153 500 км. +1 200 км с начала учёта.")
    assert reply.endswith("🚗 Октавия · 153 500 км")
    r = (await h.all(OdometerReading))[0]
    assert (r.date, r.value, r.source) == (TODAY, 153_500, "manual")

    await h.text("/km")
    reply = await h.text("154 000")
    assert reply.startswith("Сохранено: 154 000 км. +500 км с 17.10.2026.")


async def test_smaller_mileage_rejected(h):
    await add_car(h)
    await h.text("/km")
    await h.text("153 000")
    await h.text("/km")
    reply = await h.text("152 000")
    assert reply == (
        "Пробег не может быть меньше текущего (153 000 км). Введите число или нажмите «Отмена»."
    )
    # The dialog goes on: a correct value is accepted
    assert (await h.text("153 100")).startswith("Сохранено")


async def test_below_initial_rejected(h):
    await add_car(h)
    await h.text("/km")
    reply = await h.text("100")
    assert reply.startswith("Пробег не может быть меньше начального (152 300 км).")


async def test_mileage_for_another_date(h):
    await add_car(h, mileage="150 000")
    await h.text("/km")
    await h.text("153 000")
    await h.text("/km")
    await h.press("📅 Другая дата")
    await h.text("10.10")
    reply = await h.text("154 000")
    assert "не может быть больше 153 000 км" in reply and "17.10.2026" in reply
    reply = await h.text("151 000")
    assert reply.startswith("Сохранено: 151 000 км, 10.10.2026. +1 000 км с начала учёта.")
    # The latest date still decides the current mileage
    assert reply.endswith("· 153 000 км")


async def test_yesterday_button(h):
    await add_car(h)
    await h.text("/km")
    await h.press("📅 Другая дата")
    await h.press("Вчера")
    await h.text("152 400")
    assert (await h.all(OdometerReading))[0].date == date(2026, 10, 16)


async def test_mileage_format_error(h):
    await add_car(h)
    await h.text("/km")
    reply = await h.text("152.5")
    assert reply.startswith("Нужно число")
    assert await h.all(OdometerReading) == []


async def test_history_paging_and_average(h, now):
    await add_car(h, mileage="100 000")
    for day in range(1, 13):
        await h.text("/km")
        await h.press("📅 Другая дата")
        await h.text(f"{day:02d}.10.2026")
        await h.text(str(100_000 + day * 100))
    await h.text("/km")
    reply = await h.press("📈 История")
    assert "12.10.2026 — 101 200 км" in reply
    assert "Начальный пробег" not in reply  # on the last page
    assert "1/2" in h.buttons()
    reply = await h.press("›")
    assert "02.10.2026 — 100 200 км" in reply and "Начальный пробег — 100 000 км" in reply
    assert "В среднем" not in reply  # 11 days are not enough for an average


async def test_edit_and_delete_reading(h):
    await add_car(h, mileage="150 000")
    await h.text("/km")
    await h.text("152 300")
    await h.text("/km")
    await h.press("📈 История")
    await h.press("17.10.26 · 152 300")
    await h.press("Изменить пробег")
    reply = await h.text("149 000")
    assert "меньше начального" in reply
    reply = await h.text("152 030")
    assert reply.startswith("Исправлено: 152 030 км, 17.10.2026.")
    await h.press("17.10.26 · 152 030")
    await h.press("Изменить дату")
    assert (await h.text("завтра")).startswith("Не понял дату")
    await h.text("15.10")
    assert (await h.all(OdometerReading))[0].date == date(2026, 10, 15)
    await h.press("15.10.26 · 152 030")
    await h.press("Удалить")
    await h.press("Да, удалить")
    assert await h.all(OdometerReading) == []
    assert views.READING_DELETED in h.last_plain()


# --- settings ---


async def test_settings_timezone_and_currency(h):
    await add_car(h)
    reply = await h.text("⚙️ Настройки")
    assert "Москва (Europe/Moscow, UTC+3)" in reply and "Валюта: RUB" in reply
    await h.press("🕒 Часовой пояс")
    await h.press("Екатеринбург")
    await h.press("💱 Валюта")
    await h.text("gel")
    s = await _settings(h)
    assert (s.timezone, s.currency) == ("Asia/Yekaterinburg", "GEL")
    assert "Екатеринбург (Asia/Yekaterinburg, UTC+5)" in h.last_plain()


async def test_settings_typed_timezone(h):
    await h.text("/settings")
    await h.press("🕒 Часовой пояс")
    assert (await h.text("Mars/Base")) == views.TZ_UNKNOWN.replace("<code>", "").replace(
        "</code>", ""
    )
    await h.text("Asia/Almaty")
    assert (await _settings(h)).timezone == "Asia/Almaty"


async def test_timezone_moves_today(h, now):
    """«Today» for a reading is the owner's local date, not the UTC one."""
    await add_car(h)
    await h.text("/settings")
    await h.press("🕒 Часовой пояс")
    await h.press("Камчатка")  # UTC+12: 19:00 on 17.10
    now.set(datetime(2026, 10, 17, 13, 0, tzinfo=UTC))  # 01:00 on 18.10 in Kamchatka
    await h.text("/km")
    await h.text("152 500")
    assert (await h.all(OdometerReading))[0].date == date(2026, 10, 18)


async def test_settings_created_for_owner(h):
    await h.text("/menu")
    s = await _settings(h)
    assert (s.timezone, s.currency) == ("Europe/Moscow", "RUB")
    assert len(await h.all(User)) == 1
