# 04. Тесты

Два уровня:
- **юнит** — чистые функции из `services/` (без БД и сети);
- **диалоги** — настоящий `Dispatcher` и хэндлеры, временная SQLite, фейковый Telegram,
  фейковые внешние API, управляемые часы. Ни одного сетевого вызова.

Запуск: `python -m pytest` локально, `docker build --target test .` — как в CI.

## tests/tg_fakes.py — фейковая сеть Telegram
Подкласс `aiogram.client.session.base.BaseSession`: копит все запросы, на `SendMessage`
возвращает `Message`, на остальное — `True`. `fail_next` — бросить исключение на следующем
запросе (проверка повторов при `TelegramNetworkError`).
```python
OWNER_ID = 1000
STRANGER_ID = 2000

class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        # Set to an exception to make the next request fail with it
        self.fail_next: Exception | None = None

    # Signature is fixed by aiogram's BaseSession
    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        self.requests.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=next(_ids), date=datetime.now(UTC),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self) -> None:
        pass

    def texts(self) -> list[str]:
        return [m.text for m in self.requests if isinstance(m, SendMessage | EditMessageText)]
```
Плюс фабрики апдейтов: `text_update(text, user_id)`, `callback_update(data, user_id,
inaccessible=False)` (`InaccessibleMessage` — старое сообщение, которое уже нельзя
редактировать), `sticker_update(...)` для проверки fallback-хэндлера.

## tests/harness.py — драйвер диалога
```python
class Harness:
    async def feed(self, update):        # dp.feed_update(bot, update, sessionmaker=..., db_lock=..., <clients>=...)
    async def text(self, text) -> str | None   # отправить текст, вернуть ответ бота без HTML
    async def tap(self, data) -> str | None    # нажать inline-кнопку с callback_data
    async def all(self, model)                 # все строки таблицы
    async def tick(self)                       # один тик планировщика на текущем времени
```
Важные детали:
- `build_dispatcher` вызывается **один раз на процесс** (`@functools.cache`): роутеры —
  модульные объекты и цепляются только к одному родителю.
- Изоляция FSM между тестами — новый bot id на каждый тест:
  `Bot(token=f"{next(_bot_ids)}:TEST", session=FakeSession())`.
- БД — файл в `tmp_path`, не `:memory:` (каждый апдейт открывает своё соединение, а
  `:memory:` у каждого соединения своя). Схема — `Base.metadata.create_all`.
- Внешние API подставляются через workflow data (`subs_client=FakeSubsClient()`) или
  `monkeypatch.setattr(...)` в `autouse`-фикстуре, чтобы тест физически не мог сходить в сеть.
  Фейк умеет `down = True` и считает `calls`.
- `onboard(h)` — хелпер, проходящий стартовый сценарий, чтобы каждый тест не повторял его.

## tests/conftest.py — часы и проверка HTML
```python
NOW = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)  # фиксированный момент, с комментарием что это за день

@pytest.fixture
def now():
    """A controllable clock: ``now.set(datetime)`` moves time for the bot."""
    class Clock:
        value = NOW
        def set(self, value: datetime) -> None:
            self.value = value
    c = Clock()
    clock.set_clock(lambda: c.value)
    yield c
    clock.set_clock(lambda: datetime.now(UTC))

@pytest.fixture
async def h(tmp_path, now):
    harness, engine = await make_harness(tmp_path / "t.db", now)
    yield harness
    # Telegram rejects the whole message on broken markup
    for text in harness.net.texts():
        check_telegram_html(text)
    await engine.dispose()
```
`check_telegram_html` — `HTMLParser`, который падает на теге не из списка Telegram
(`b i u s code pre a blockquote tg-spoiler`), на несбалансированных и вложенных `blockquote`.
Проверяется **каждое** сообщение каждого теста автоматически — битая разметка ловится до прода.

`plain(text)` — убрать теги и заменить NBSP на пробел, чтобы сравнивать ответы как текст.

## Пример диалогового теста
```python
async def test_stranger_is_ignored(h):
    assert await h.text("/start", user_id=STRANGER_ID) is None
    assert await h.all(User) == []

async def test_reminder_next_evening(h, now):
    await onboard(h)
    now.set(datetime(2026, 10, 18, 18, 0, tzinfo=UTC))  # 21:00 МСК следующего дня
    await h.tick()
    assert "остатки" in h.last_plain()
```

## Что стоит покрывать в любом боте
- whitelist: чужой пользователь не получает ответа и не создаёт строк в БД;
- `/cancel` и неизвестный ввод в каждом состоянии FSM;
- нажатие кнопки на старом (`inaccessible`) сообщении;
- планировщик: уведомление уходит один раз, повторяется после сетевой ошибки
  (`net.fail_next = TelegramNetworkError(...)`), не уходит повторно после рестарта;
- внешний API недоступен (`fake.down = True`) — бот работает, показывает устаревшие данные/ошибку;
- `record_startup`: новая версия, рестарт той же, откат с `FAILED_VERSION`.
