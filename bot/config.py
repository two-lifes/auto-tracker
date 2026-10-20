import logging
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DB_FILENAME = "auto_tracker.db"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


class ConfigError(RuntimeError):
    pass


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
    allowed_user_ids: frozenset[int]
    data_dir: Path
    default_tz: str = "Europe/Moscow"
    log_level: int = logging.INFO
    # e.g. socks5://user:pass@host:port; None means direct connection
    proxy_url: str | None = None
    # Baked into the Docker image by CI; empty for local runs
    app_version: str | None = None
    app_title: str | None = None
    # Set by deploy.sh when it rolled back from this version
    failed_version: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"


def parse_user_ids(raw: str) -> frozenset[int]:
    try:
        ids = frozenset(int(part) for part in raw.split(",") if part.strip())
    except ValueError:
        raise ConfigError(
            "ALLOWED_USER_IDS must be numeric Telegram user ids separated by commas"
        ) from None
    if not ids:
        raise ConfigError("ALLOWED_USER_IDS is not set")
    return ids


def load_config() -> Config:
    _load_dotenv(Path(".env"))
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN is not set")
    allowed = parse_user_ids(os.environ.get("ALLOWED_USER_IDS", ""))
    tz = _optional("DEFAULT_TZ") or "Europe/Moscow"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"DEFAULT_TZ: unknown time zone {tz!r}") from None
    level = (_optional("LOG_LEVEL") or "INFO").upper()
    if level not in LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
    data_dir = Path(_optional("DATA_DIR") or "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        bot_token=token,
        allowed_user_ids=allowed,
        data_dir=data_dir,
        default_tz=tz,
        log_level=logging.getLevelName(level),
        proxy_url=_optional("PROXY_URL"),
        app_version=_optional("APP_VERSION"),
        app_title=_optional("APP_TITLE"),
        failed_version=_optional("FAILED_VERSION"),
    )


def _optional(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None
