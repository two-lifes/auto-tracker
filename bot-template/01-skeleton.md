# 01. Каркас проекта

## Структура
```
.dockerignore  .gitattributes  .gitignore  .env.example  .env (не в git)
pyproject.toml  alembic.ini  Dockerfile  docker-compose.yml   # локальный compose
CLAUDE.md
.github/workflows/ci-cd.yml
deploy/docker-compose.yml  deploy/deploy.sh                    # прод
migrations/env.py  migrations/script.py.mako  migrations/versions/
bot/
  __main__.py      # конфиг → миграции → запуск polling + планировщик
  app.py           # build_dispatcher: middlewares, on_error, роутеры
  config.py        # Config + load_config, свой мини-парсер .env
  clock.py         # единственный источник времени (подменяется в тестах)
  scheduler.py     # фоновый цикл раз в 60 с
  views.py         # все тексты сообщений
  db/ models.py repo.py session.py
  middlewares/ auth.py (whitelist) db.py (сессия + lock)
  handlers/ keyboards/ services/ integrations/
tests/ conftest.py harness.py tg_fakes.py test_*.py
docs/
```
Принцип: чистая логика в `services/` без I/O (легко тестировать), Telegram — в `handlers/`,
все тексты — в `views.py`, внешние API — в `integrations/`.

## pyproject.toml
Зависимости закреплены точными версиями (`==`) — образ воспроизводим. У каждой неочевидной
зависимости комментарий «зачем».
```toml
[project]
name = "<bot>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "aiogram==3.31.0",
    # Required by aiogram's AiohttpSession for proxy support
    "aiohttp-socks==0.12.0",
    "sqlalchemy[asyncio]==2.1.4",
    "aiosqlite==0.22.1",
    "alembic==1.20.0",
    "httpx==0.28.1",
    "tzdata==2026.5",   # zoneinfo в slim-образе
]

[project.optional-dependencies]
dev = ["pytest==9.1.1", "pytest-asyncio==1.4.0", "ruff==0.17.1"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["bot*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["migrations/versions"]   # автоген Alembic

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "ASYNC"]
```
Версии выше — те, что стоят в finance_tracker на момент написания; для нового бота проверить
актуальные.

## Служебные файлы
`.gitignore`
```
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.ruff_cache/
.env
data/
*.db
```
`.dockerignore` — то же плюс `.git`, чтобы `.env` и БД никогда не попали в образ:
```
.venv
.git
.env
data
**/__pycache__
.pytest_cache
.ruff_cache
*.egg-info
```
`.gitattributes` — иначе checkout на Windows даст CRLF и `deploy.sh` упадёт на Linux:
```
*.sh text eol=lf
```

## .env и .env.example
`.env.example` в git — документация всех переменных: комментарий над каждой, пустые значения
для секретов. `.env` — только локально и на сервере.
```
# Token from @BotFather
BOT_TOKEN=
# Your numeric Telegram id (e.g. from @userinfobot); the bot ignores everyone else
ALLOWED_USER_ID=
# Optional proxy for Telegram API: socks5://user:pass@host:port or http://user:pass@host:port
PROXY_URL=
# SQLite file location
DB_PATH=data/<db>

# Optional integration. Empty values turn the feature off.
SOME_API_URL=
SOME_API_TOKEN=
```
Переменные, которые **не** пишутся в `.env` руками: `APP_VERSION`, `APP_TITLE` (зашиваются
в образ CI), `FAILED_VERSION` (ставит `deploy.sh` при откате). `DB_PATH` в контейнере
переопределяется на `/data/<db>` в compose.

## Конфиг: `bot/config.py`
- Свой парсер `.env` (без python-dotenv): локально нет Docker `env_file`, а реальные переменные
  окружения всегда главнее (`os.environ.setdefault`).
- Неизменяемый `@dataclass(frozen=True) Config`; ошибки → `ConfigError` с понятным текстом,
  `run()` логирует его и выходит с кодом 1 (контейнер не стартует → deploy.sh откатит).
- Опциональные интеграции: пустое значение = выключено, без падения.
```python
def _load_dotenv(path: Path) -> None:
    # Locally there is no Docker env_file, so read KEY=VALUE pairs ourselves;
    # real environment variables always win.
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Config:
    bot_token: str
    allowed_user_id: int
    db_path: Path
    proxy_url: str | None = None
    # Baked into the Docker image by CI; empty for local runs
    app_version: str | None = None
    app_title: str | None = None
    # Set by deploy.sh when it rolled back from this version
    failed_version: str | None = None

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"


def load_config() -> Config:
    _load_dotenv(Path(".env"))
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN is not set")
    try:
        allowed_user_id = int(os.environ.get("ALLOWED_USER_ID", "").strip())
    except ValueError:
        raise ConfigError("ALLOWED_USER_ID must be a numeric Telegram user id") from None
    db_path = Path(os.environ.get("DB_PATH", "data/<db>"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Config(
        bot_token=token,
        allowed_user_id=allowed_user_id,
        db_path=db_path,
        proxy_url=_optional("PROXY_URL"),
        app_version=_optional("APP_VERSION"),
        app_title=_optional("APP_TITLE"),
        failed_version=_optional("FAILED_VERSION"),
    )


def _optional(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None
```

## Точка входа: `bot/__main__.py`
Порядок важен:
1. `logging.basicConfig(level=INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`
   — stdout читает `docker compose logs`, а `deploy.sh` ищет там `Run polling`.
2. `load_config()`; `ConfigError` → лог + `sys.exit(1)`.
3. Миграции **до** `asyncio.run` (async env Alembic сам вызывает `asyncio.run`):
   ```python
   def run_migrations(config: Config) -> None:
       alembic_cfg = AlembicConfig("alembic.ini")
       alembic_cfg.set_main_option("sqlalchemy.url", config.db_url)
       # Otherwise alembic.ini's logging config would silence the bot's INFO logs
       alembic_cfg.attributes["configure_logger"] = False
       command.upgrade(alembic_cfg, "head")
   ```
4. `main()`: engine/sessionmaker → `record_startup(...)` (см. 03) → `Bot` с
   `AiohttpSession(proxy=...)` если задан прокси и `DefaultBotProperties(parse_mode=HTML)` →
   `build_dispatcher` → `dp["sessionmaker"]`, `dp["db_lock"] = asyncio.Lock()`, клиенты API →
   `set_my_commands` (сетевую ошибку только логировать — меню не критично) → фоновая задача
   планировщика → `dp.start_polling(bot)`.
5. `finally`: отменить планировщик и дождаться его, закрыть HTTP-клиенты,
   `bot.session.close()`, `engine.dispose()`.

## Dispatcher: `bot/app.py`
```python
def build_dispatcher(allowed_user_id: int) -> Dispatcher:
    dp = Dispatcher()
    # Whitelist runs first so strangers never touch the database
    dp.update.outer_middleware(WhitelistMiddleware(allowed_user_id))
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.errors.register(on_error)
    dp.include_router(build_router())
    return dp
```
- `WhitelistMiddleware`: если `data["event_from_user"].id != allowed_user_id` → лог и `return None`.
- `DbSessionMiddleware`: `async with db_lock, sessionmaker() as session, session.begin():` —
  у каждого апдейта своя транзакция, коммит при успехе, откат при исключении. Тот же `db_lock`
  берёт планировщик → нет `database is locked` в SQLite.
- `on_error`: `log.exception(...)` и пользователю «Что-то пошло не так, попробуйте ещё раз.»
  (alert на callback или ответ на сообщение), `TelegramAPIError` при этом только логировать.

## БД и миграции
- `bot/db/session.py`: включить `PRAGMA foreign_keys=ON` на каждом соединении (иначе SQLite
  игнорирует FK и `ON DELETE CASCADE`); `async_sessionmaker(engine, expire_on_commit=False)`.
- `migrations/env.py` (из `alembic init -t async`), правки:
  - `target_metadata = Base.metadata`;
  - URL, если не передан ботом, берётся из `DB_PATH` — чтобы работал CLI `alembic revision`;
  - `render_as_batch=True` в обоих режимах — SQLite не умеет ALTER, batch пересоздаёт таблицы;
  - `fileConfig` только если `config.attributes.get("configure_logger", True)`.
- `alembic.ini`: `script_location = %(here)s/migrations`, `prepend_sys_path = .`,
  `sqlalchemy.url =` пустой (комментарий: задаётся из `DB_PATH`).
- Миграции применяются при каждом старте бота; перед стартом новой версии `deploy.sh` делает
  бэкап, поэтому откат безопасен.

## Время: `bot/clock.py`
Никаких `datetime.now()` в коде — только `utcnow()`; тесты подменяют источник через `set_clock`.
```python
_clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731

def utcnow() -> datetime:
    return _clock()

def set_clock(clock: Callable[[], datetime]) -> None:
    global _clock
    _clock = clock

def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they were written as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
```
В БД храним UTC (`DateTime(timezone=True)`), локальная дата — через таймзону пользователя.

## Планировщик: `bot/scheduler.py`
- Бесконечный цикл `tick()` раз в 60 с; любое исключение тика логируется и не убивает цикл,
  `CancelledError` пробрасывается.
- Сообщения от бота — через таблицу `notifications`: `plan` вставляет `pending` с уникальным
  ключом (at-most-once после рестартов), `deliver` отправляет и ставит `sent`/`skipped`.
  Сетевые ошибки Telegram (`TelegramNetworkError`, `RetryAfter`, `ServerError`) → откат и повтор
  на следующем тике; `Forbidden`/`BadRequest` → `skipped`.
- Сетевые вызовы внешних API — **вне** `db_lock`, запись результата — под ним.
