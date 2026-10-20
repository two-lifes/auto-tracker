# Шаблон обслуживания Telegram-бота

Всё, что не относится к предметной логике finance_tracker, но делает бота удобным в жизни:
конфиг из `.env`, Docker, тесты в CI, автодеплой по push в `main`, бэкап БД и автооткат,
уведомление владельца о новой версии, офлайн-тесты диалогов.

Стек: Python 3.12, aiogram 3, SQLAlchemy 2 async + aiosqlite, Alembic, httpx, pytest, ruff,
Docker, GitHub Actions, GHCR, сервер с Docker по SSH.

## Файлы
1. [01-skeleton.md](01-skeleton.md) — структура проекта, `pyproject.toml`, `.env`, конфиг,
   точка входа, whitelist, обработка ошибок, БД и миграции, часы.
2. [02-docker-ci-deploy.md](02-docker-ci-deploy.md) — Dockerfile, compose, GitHub Actions,
   `deploy.sh` (бэкап, проверка старта, откат), первичная настройка сервера и GitHub.
3. [03-version-notices.md](03-version-notices.md) — «🔄 Бот обновлён до версии …» и история обновлений.
4. [04-testing.md](04-testing.md) — фейковый Telegram, управляемые часы, проверка HTML.
5. [05-claude-md.md](05-claude-md.md) — шаблон `CLAUDE.md` для нового проекта.

## Как это работает целиком
```
git push main
  └─ GitHub Actions
       ├─ job test:   docker build --target test   (pytest + ruff на Python прод-образа)
       └─ job deploy: build --target runtime (APP_VERSION=sha, APP_TITLE=тема коммита)
                      → push ghcr.io/<owner>/<bot>:<sha> и :latest
                      → scp deploy/docker-compose.yml deploy/deploy.sh на сервер
                      → ssh: bash deploy.sh <sha>
                           pull → stop → бэкап БД → up → ждём "Run polling" в логах
                           ├─ ок:     запомнить тег, удалить старые образы
                           └─ ошибка: вернуть бэкап БД, поднять прошлый тег с FAILED_VERSION
  └─ бот при старте: миграции → запись в таблицу deployments
     → планировщик пишет владельцу «🔄 обновлён» или «⚠️ не запустилось, откатились»
```

## Чек-лист нового бота
- [ ] Скопировать инфраструктурные файлы (список в 01 и 02), заменить плейсхолдеры:
      `<bot>` (имя репо/папки/образа, напр. `habit_tracker`), `<owner>` (GitHub-владелец в нижнем
      регистре), `<db>` (имя файла БД, напр. `habits.db`).
- [ ] `bot/config.py`: убрать чужие переменные, добавить свои; синхронно обновить `.env.example`.
- [ ] `alembic revision --autogenerate -m "initial schema"` после первой модели.
- [ ] Локально: `.env` → `python -m bot` → `/start` в Telegram.
- [ ] GitHub: environment `production`, секреты SSH, переменная `DEPLOY_ENABLED=true` (см. 02).
- [ ] Сервер: папка `/opt/<bot>`, `.env`, `data/` с владельцем uid 1000 (см. 02).
- [ ] Первый push в `main` → проверить, что пришло «🔄 Бот обновлён до версии …».
