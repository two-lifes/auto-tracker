# 05. Шаблон CLAUDE.md

Положить в корень нового проекта и заполнить `<...>`. Разделы Commands, Deploy и общие
Conventions переносятся как есть; Layout и предметные правила — свои.

```markdown
# <bot>

<Одна-две строки: что делает бот.> Personal Telegram bot (aiogram 3). Single user (whitelist by
`ALLOWED_USER_ID`). User-facing text is Russian.

## Commands (Windows, from project root)
- Install: `python -m venv .venv; .\.venv\Scripts\python -m pip install -e ".[dev]"`
- Run bot: `.\.venv\Scripts\python -m bot` (applies migrations on start; needs `.env`, see `.env.example`)
- Tests: `.\.venv\Scripts\python -m pytest`
- Lint: `.\.venv\Scripts\ruff check .`
- New migration: `.\.venv\Scripts\alembic revision --autogenerate -m "..."` (uses `DB_PATH`)
- Tests on Python 3.12 in Docker: `docker build --target test .`

## Layout
- `bot/services/` — logic. Pure (no I/O, unit-tested): <...>. DB-backed: <...>, `notifications`,
  `deployments`.
- `bot/handlers/` — Telegram; `bot/views.py` — all message texts; `bot/keyboards/` — buttons.
- `bot/scheduler.py` — 60 s loop: <periodic jobs>, reminders, version notices.
- Dialog tests: `tests/test_flows.py` via `tests/harness.py` (fake Telegram, fake external APIs,
  controllable clock).

## Conventions
- Time only via `bot.clock.utcnow()`; datetimes in SQLite are UTC (`as_utc`).
- Bot-initiated messages go through the `notifications` table (plan → deliver), never sent directly.
- Network calls in the scheduler run outside `db_lock`; handlers may call external APIs (5 s timeout).
- Messages use Telegram HTML; escape user/external text with `html.escape`.
- <предметные правила: деньги в int, и т.п.>

## Deploy
push to main → GitHub Actions (tests in Docker) → image `ghcr.io/<owner>/<bot>` →
SSH → `deploy/deploy.sh` in `/opt/<bot>` (DB backup, wait for "Run polling", rollback on failure).
Server state: `.env`, `data/`, `backups/`, `.deployed_tag`. Deploys are off until the repository
variable `DEPLOY_ENABLED=true`.
```
