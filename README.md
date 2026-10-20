# Автодневник

Личный Telegram-бот: история обслуживания автомобиля, пробег, фото и напоминания.
Требования и план — в [`docs/`](docs/), статус этапов — в [`docs/progress.md`](docs/progress.md).

Стек: Python 3.12, aiogram 3, SQLite (SQLAlchemy 2 async + Alembic), Docker Compose,
GitHub Actions → GHCR → VPS по SSH. Обновления от Telegram — long polling (без домена и входящих портов).

## Конфигурация
Все переменные описаны в [`.env.example`](.env.example). Скопируйте его в `.env` и заполните:
- `BOT_TOKEN` — токен от @BotFather;
- `ALLOWED_USER_IDS` — ваш Telegram ID (несколько — через запятую); остальным бот не отвечает;
- `DATA_DIR` — каталог данных (БД `auto_tracker.db`, позже фото и бэкапы);
- `DEFAULT_TZ`, `LOG_LEVEL`, `PROXY_URL` — по необходимости.

`.env` и `data/` в git не попадают.

## Локальный запуск (Windows)
```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env   # заполнить
.\.venv\Scripts\python -m bot
```
Миграции БД применяются автоматически при старте. В Telegram: `/start`.

Тесты и линтер:
```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
docker build --target test .   # то же на Python 3.12, как в CI
```
Локально в Docker: `docker compose up -d --build`.

## Как устроено развёртывание
```
git push main → GitHub Actions
  test:   docker build --target test (pytest + ruff)
  deploy: образ ghcr.io/two-lifes/auto_tracker:<sha> → scp deploy/* на сервер → bash deploy.sh <sha>
          pull → stop → копия БД в backups/ → up → ждём "Run polling"
          ├─ ок:     запоминаем тег, удаляем старые образы
          └─ ошибка: возвращаем копию БД, поднимаем прошлую версию
бот при старте: миграции → пишет владельцу «🔄 Бот обновлён до версии …» или «⚠️ … не запустилось»
```
Деплой выключен, пока в репозитории не задана переменная `DEPLOY_ENABLED=true`.

## Первичная настройка (один раз)

### Сервер
Нужны Docker с Compose и пользователь деплоя в группе `docker`.
```bash
sudo mkdir -p /opt/auto_tracker/data
sudo chown -R <deploy_user> /opt/auto_tracker
sudo chown 1000:1000 /opt/auto_tracker/data   # контейнер работает под uid 1000
nano /opt/auto_tracker/.env                   # заполнить по .env.example
chmod 600 /opt/auto_tracker/.env
sudo systemctl enable docker                  # Docker стартует при загрузке, бот — вместе с ним
```
`DATA_DIR` в серверном `.env` не нужен: compose задаёт `/data`.
Если пакет образа в GHCR приватный — `docker login ghcr.io` на сервере токеном с `read:packages`.

### Ключ деплоя (на своей машине)
Можно взять тот же ключ, что у других ботов на этом сервере.
```bash
ssh-keygen -t ed25519 -N "" -f deploy_key -C "auto_tracker-deploy"
# deploy_key.pub → ~/.ssh/authorized_keys пользователя деплоя
ssh-keyscan -p 22 <host>   # вывод → секрет SSH_KNOWN_HOSTS
```

### GitHub (Settings репозитория `two-lifes/auto_tracker`)
- Environments → `production`.
- Secrets: `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` (содержимое `deploy_key`), `SSH_KNOWN_HOSTS`,
  при необходимости `SSH_PORT` (по умолчанию 22).
- Variables: `DEPLOY_ENABLED=true`; при необходимости `DEPLOY_DIR` (по умолчанию `/opt/auto_tracker`).

## Обновление
Обычное: `git push` в `main`. Тема коммита приходит владельцу в уведомлении об обновлении.
Повторный деплой без коммита: Actions → CI/CD → Run workflow.

## Эксплуатация
- Логи: `cd /opt/auto_tracker && docker compose logs -f --tail 100 bot`
  (ротация: 3 файла по 10 МБ).
- Состояние бота: команда `/status` в Telegram (версия, время работы).
- Ручной откат: `bash /opt/auto_tracker/deploy.sh <старый_sha>` (на сервере хранятся текущий и
  предыдущий образы). Схема БД при этом не откатывается — при необходимости при остановленном боте
  верните файл из `/opt/auto_tracker/backups/` в `data/auto_tracker.db`.
- Состояние на сервере: `.env`, `data/`, `backups/`, `.deployed_tag`; `docker-compose.yml` и
  `deploy.sh` перезаписываются каждым деплоем.

Полноценные ежедневные бэкапы и инструкция восстановления — этап 4.
