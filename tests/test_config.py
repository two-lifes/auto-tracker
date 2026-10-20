import logging
from datetime import timedelta

import pytest

from bot.config import ConfigError, load_config, parse_user_ids
from bot.views import format_duration


@pytest.fixture
def env(monkeypatch, tmp_path):
    # load_config reads .env from the working directory; an empty dir keeps the real one out
    monkeypatch.chdir(tmp_path)
    for name in ("BOT_TOKEN", "ALLOWED_USER_IDS", "DATA_DIR", "DEFAULT_TZ", "LOG_LEVEL",
                 "PROXY_URL", "APP_VERSION", "APP_TITLE", "FAILED_VERSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1000")
    return monkeypatch


def test_parse_user_ids():
    assert parse_user_ids("1000") == {1000}
    assert parse_user_ids(" 1000, 2000 ,") == {1000, 2000}


@pytest.mark.parametrize("raw", ["", " , ", "abc", "1000;2000"])
def test_parse_user_ids_rejects(raw):
    with pytest.raises(ConfigError):
        parse_user_ids(raw)


def test_defaults(env, tmp_path):
    config = load_config()
    assert config.allowed_user_ids == {1000}
    assert config.db_path.as_posix() == "data/auto_tracker.db"
    assert (tmp_path / "data").is_dir()
    assert config.default_tz == "Europe/Moscow"
    assert config.log_level == logging.INFO
    assert config.app_version is None


def test_dotenv_file_is_read_but_env_wins(env, tmp_path):
    env.delenv("ALLOWED_USER_IDS")
    (tmp_path / ".env").write_text(
        "# comment\nALLOWED_USER_IDS=1,2\nBOT_TOKEN='from-file'\n", encoding="utf-8"
    )
    config = load_config()
    assert config.allowed_user_ids == {1, 2}
    assert config.bot_token == "123:abc"


@pytest.mark.parametrize(
    ("name", "value"),
    [("BOT_TOKEN", ""), ("ALLOWED_USER_IDS", "x"), ("DEFAULT_TZ", "Mars/Base"),
     ("LOG_LEVEL", "LOUD")],
)
def test_invalid_values(env, name, value):
    env.setenv(name, value)
    with pytest.raises(ConfigError):
        load_config()


def test_format_duration():
    assert format_duration(timedelta(seconds=30)) == "0 мин"
    assert format_duration(timedelta(hours=1, minutes=2)) == "1 ч 2 мин"
    assert format_duration(timedelta(days=3, hours=4, minutes=5)) == "3 д 4 ч"
