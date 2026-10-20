# 02. Docker, CI/CD, деплой

Плейсхолдеры: `<bot>` — имя образа/папки, `<owner>` — GitHub-владелец (в нижнем регистре,
GHCR требует), `<db>` — имя файла SQLite.

## Dockerfile
Три стадии: `base` (код + зависимости), `test` (pytest + ruff на том же Python, что в проде),
`runtime` (не-root пользователь uid 1000, том `/data`). Версия передаётся последней, чтобы новый
коммит не сбрасывал кэш слоёв.
```dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DB_PATH=/data/<db>

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY bot ./bot
COPY migrations ./migrations
RUN pip install .

# `docker build --target test .` runs the test suite and linter on the image's Python
FROM base AS test
RUN pip install ".[dev]"
COPY tests ./tests
RUN python -m pytest -q && ruff check bot tests

FROM base AS runtime
RUN useradd --create-home --uid 1000 bot && mkdir -p /data && chown bot /data
USER bot
VOLUME ["/data"]
# Set by CI; last, so a new commit doesn't invalidate the cached layers above
ARG APP_VERSION=
ARG APP_TITLE=
ENV APP_VERSION=$APP_VERSION \
    APP_TITLE=$APP_TITLE
CMD ["python", "-m", "bot"]
```

## docker-compose.yml (локально)
`docker compose up -d --build`
```yaml
services:
  bot:
    build:
      context: .
      target: runtime
    env_file: .env
    environment:
      DB_PATH: /data/<db>
    volumes:
      - ./data:/data
    restart: unless-stopped
```

## deploy/docker-compose.yml (прод)
CI копирует его на сервер; секреты только в `.env` рядом на сервере. Ротация логов обязательна,
иначе json-логи съедят диск.
```yaml
services:
  bot:
    image: ghcr.io/<owner>/<bot>:${IMAGE_TAG:-latest}
    env_file: .env
    environment:
      DB_PATH: /data/<db>
      # Set by deploy.sh on rollback so the bot can report the failed version
      FAILED_VERSION: ${FAILED_VERSION:-}
    volumes:
      - ./data:/data
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: 10m
        max-file: "3"
```
Если боту нужен API другого бота на том же сервере — общая внешняя сеть, порты не публикуются:
```yaml
    networks:
      - bots_internal
networks:
  bots_internal:
    external: true
```
Бот-сервер API слушает `0.0.0.0` и подключается к той же сети с алиасом (напр. `subs-api`),
клиент ходит на `http://subs-api:8080`. Сеть создаёт `deploy.sh` того бота, что деплоится первым.

## .github/workflows/ci-cd.yml
- `test` — на каждый push и PR; `deploy` — только `main`, только после `test`, только если
  репозиторная переменная `DEPLOY_ENABLED == 'true'` (до настройки сервера деплой выключен).
- `concurrency` — два деплоя одновременно не идут.
- В образ зашиваются `APP_VERSION` (sha) и `APP_TITLE` (тема коммита) — для уведомления (03).
- Ключ SSH чистится от CRLF и проверяется до использования; `StrictHostKeyChecking=yes` +
  `known_hosts` из секрета.
```yaml
name: CI/CD

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

env:
  IMAGE: ghcr.io/<owner>/<bot>

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-buildx-action@v4
      # Runs pytest and ruff inside the same Python image that goes to production
      - uses: docker/build-push-action@v7
        with:
          context: .
          target: test
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    needs: test
    # DEPLOY_ENABLED is a repository variable: deploys stay off until the server secrets are set
    if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request' && vars.DEPLOY_ENABLED == 'true'
    runs-on: ubuntu-latest
    environment: production
    # Two deploys must never run on the server at the same time
    concurrency:
      group: deploy-production
      cancel-in-progress: false
    permissions:
      contents: read
      packages: write
    env:
      DEPLOY_DIR: ${{ vars.DEPLOY_DIR || '/opt/<bot>' }}
      SSH_PORT: ${{ secrets.SSH_PORT || '22' }}
      TARGET: ${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }}
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Read commit subject
        id: commit
        run: echo "title=$(git log -1 --format=%s)" >> "$GITHUB_OUTPUT"
      - uses: docker/build-push-action@v7
        with:
          context: .
          target: runtime
          push: true
          # The bot reports its version to the owner after a successful deploy
          build-args: |
            APP_VERSION=${{ github.sha }}
            APP_TITLE=${{ steps.commit.outputs.title }}
          tags: |
            ${{ env.IMAGE }}:${{ github.sha }}
            ${{ env.IMAGE }}:latest
          labels: org.opencontainers.image.source=https://github.com/${{ github.repository }}
          cache-from: type=gha

      - name: Configure SSH
        env:
          SSH_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
          SSH_KNOWN_HOSTS: ${{ secrets.SSH_KNOWN_HOSTS }}
        run: |
          install -m 700 -d ~/.ssh
          # A key pasted from Windows may carry CRLF line endings, which OpenSSH rejects
          printf '%s\n' "$SSH_KEY" | tr -d '\r' > ~/.ssh/id_deploy
          chmod 600 ~/.ssh/id_deploy
          if ! ssh-keygen -y -P '' -f ~/.ssh/id_deploy > /dev/null; then
            echo "::error::SSH_PRIVATE_KEY is not a valid passphrase-less OpenSSH private key"
            exit 1
          fi
          printf '%s\n' "$SSH_KNOWN_HOSTS" > ~/.ssh/known_hosts

      - name: Deploy
        run: |
          KEY="$HOME/.ssh/id_deploy"
          scp -i "$KEY" -P "$SSH_PORT" -o StrictHostKeyChecking=yes \
            deploy/docker-compose.yml deploy/deploy.sh "$TARGET:$DEPLOY_DIR/"
          ssh -i "$KEY" -p "$SSH_PORT" -o StrictHostKeyChecking=yes \
            "$TARGET" "bash $DEPLOY_DIR/deploy.sh ${{ github.sha }}"
```
Версии actions — как в finance_tracker; для нового репо проверить актуальные.

## deploy/deploy.sh
pull → проверка прав на `data/` → stop → бэкап БД (хранится 10 последних) → up → ждать
`Run polling` (aiogram пишет его после успешного `getMe`: токен, прокси и БД в порядке) →
при успехе запомнить тег и удалить образы кроме текущего и предыдущего; при неудаче — логи,
вернуть бэкап (новая версия могла мигрировать схему) и поднять прошлый тег с `FAILED_VERSION`.
```bash
#!/usr/bin/env bash
# Deploys image tag $1 on the server; run from CI as `bash deploy.sh <tag>` in the deploy dir.
# Steps: pull -> stop -> back up the DB -> start -> wait for polling; on failure roll back.
set -euo pipefail

TAG="${1:?usage: deploy.sh <image tag>}"
IMAGE=ghcr.io/<owner>/<bot>
DB_FILE=<db>
KEEP_BACKUPS=10
STARTUP_TIMEOUT=90

cd "$(dirname "$0")"
[ -f .env ] || { echo "No .env in $PWD" >&2; exit 1; }
mkdir -p data backups
PREV_TAG=$(cat .deployed_tag 2>/dev/null || true)

# Only if the bot uses the shared network (see compose)
# docker network inspect bots_internal >/dev/null 2>&1 || docker network create bots_internal

# Pull first, so the bot is down only for the restart itself
IMAGE_TAG="$TAG" docker compose pull

# The container runs as uid 1000 and must be able to write the DB
if ! docker run --rm --user 1000 -v "$PWD/data:/data" --entrypoint sh "$IMAGE:$TAG" \
    -c 'test -w /data'; then
    echo "data/ is not writable by uid 1000, run: sudo chown 1000:1000 $PWD/data" >&2
    exit 1
fi

# Migrations run on start, so take a consistent copy while the bot is stopped
docker compose stop
BACKUP=""
if [ -f "data/$DB_FILE" ]; then
    BACKUP="backups/${DB_FILE%.db}-$(date -u +%Y%m%d-%H%M%S)-${PREV_TAG:-none}.db"
    cp "data/$DB_FILE" "$BACKUP"
    # Names start with a UTC timestamp, so a reverse sort puts the newest first
    printf '%s\n' "backups/${DB_FILE%.db}"-*.db | sort -r | tail -n +$((KEEP_BACKUPS + 1)) \
        | xargs -r rm --
    echo "DB backup: $BACKUP"
fi

wait_ready() {
    local since=$1
    for _ in $(seq "$STARTUP_TIMEOUT"); do
        # aiogram logs this after getMe succeeded: token, proxy and DB are all fine
        if docker compose logs --since "$since" bot 2>/dev/null | grep -q "Run polling"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
IMAGE_TAG="$TAG" docker compose up -d
if wait_ready "$STARTED"; then
    echo "$TAG" > .deployed_tag
    echo "Deployed $TAG"
    # Keep the current and the previous image for a quick manual rollback
    # grep exits 1 when there is nothing to remove (e.g. the first deploy)
    docker images "$IMAGE" --format '{{.Tag}}' \
        | { grep -vxF -e "$TAG" -e "${PREV_TAG:-$TAG}" || true; } \
        | xargs -r -I{} docker rmi "$IMAGE:{}"
    exit 0
fi

echo "Bot did not start within ${STARTUP_TIMEOUT}s, last logs:" >&2
docker compose logs --since "$STARTED" --tail 50 bot >&2
docker compose stop
if [ -n "$PREV_TAG" ]; then
    # The new version may have migrated the DB; the old one needs the old schema
    if [ -n "$BACKUP" ]; then
        cp "$BACKUP" "data/$DB_FILE"
    fi
    IMAGE_TAG="$PREV_TAG" FAILED_VERSION="$TAG" docker compose up -d
    echo "Rolled back to $PREV_TAG" >&2
fi
exit 1
```
В finance_tracker имя БД вписано прямо (`data/finance.db`); здесь вынесено в `DB_FILE`.

Состояние на сервере в `/opt/<bot>`: `.env`, `data/<db>`, `backups/`, `.deployed_tag`,
`docker-compose.yml` и `deploy.sh` (перезаписываются каждым деплоем).

## Первичная настройка

### Сервер (один раз)
```bash
sudo mkdir -p /opt/<bot>/data
sudo chown -R <deploy_user> /opt/<bot>
sudo chown 1000:1000 /opt/<bot>/data      # контейнер работает под uid 1000
nano /opt/<bot>/.env                      # заполнить по .env.example; chmod 600
```
Пользователь деплоя должен иметь доступ к Docker (группа `docker`). Если пакет образа в GHCR
приватный — на сервере нужен `docker login ghcr.io` с токеном, у которого есть `read:packages`;
публичный пакет тянется без логина.

### Ключ деплоя (на своей машине)
```bash
ssh-keygen -t ed25519 -N "" -f deploy_key -C "<bot>-deploy"   # ключ без пароля
# deploy_key.pub → ~/.ssh/authorized_keys пользователя деплоя на сервере
ssh-keyscan -p 22 <host>                                        # вывод → SSH_KNOWN_HOSTS
```
Можно один ключ на все боты на сервере.

### GitHub (Settings репозитория)
- Environments → `production`.
- Secrets (в environment или repository):
  `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` (содержимое `deploy_key`), `SSH_KNOWN_HOSTS`,
  опционально `SSH_PORT` (по умолчанию 22).
- Variables: `DEPLOY_ENABLED=true` (включает деплой), опционально `DEPLOY_DIR`
  (по умолчанию `/opt/<bot>`).
- `GITHUB_TOKEN` с `packages: write` пушит образ — отдельный секрет не нужен.

## Эксплуатация
- Логи: `cd /opt/<bot> && docker compose logs -f --tail 100 bot`.
- Ручной откат на прошлый тег: `bash deploy.sh <старый_sha>` (локально лежат текущий и
  предыдущий образы). Схема БД при этом не откатывается — при необходимости вернуть файл из
  `backups/` при остановленном боте.
- Повторный деплой без коммита: Actions → CI/CD → Run workflow (`workflow_dispatch`).
- Тесты как в CI локально: `docker build --target test .`.
