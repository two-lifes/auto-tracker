# 03. Уведомления о версиях

После каждого деплоя владелец получает в Telegram:
- `🔄 Бот обновлён до версии <code>abc1234</code>` + тема коммита;
- `⚠️ Обновление <code>abc1234</code> не запустилось. Бот вернулся на предыдущую версию.`

И может открыть историю в настройках («🔄 Обновления», с «2 часа назад»).

## Откуда данные
| Переменная | Кто ставит | Смысл |
|---|---|---|
| `APP_VERSION` | CI, `build-args` → `ENV` в Dockerfile | git sha |
| `APP_TITLE` | CI, `git log -1 --format=%s` | тема коммита |
| `FAILED_VERSION` | `deploy.sh` при откате, через compose | sha, который не стартовал |

Локальный запуск без них ничего не пишет. Поэтому темы коммитов стоит писать человеческими —
это и есть changelog для владельца.

## Модель
```python
class Deployment(Base):
    """A bot version that started on the server (ok) or failed to start and was rolled back."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(40))  # git sha
    title: Mapped[str | None] = mapped_column(String(200))  # commit subject
    status: Mapped[str] = mapped_column(String(10))  # ok / failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

## Запись при старте (`bot/services/deployments.py`)
Вызывается в `main()` сразу после создания engine. Рестарт той же версии (ребут, падение)
ничего не добавляет; после отката перезапускается последняя ok-версия — тоже ничего.
```python
async def record_startup(session, version, title, failed_version, now) -> None:
    if failed_version:
        known = await session.scalar(select(Deployment.id).where(
            Deployment.version == failed_version, Deployment.status == STATUS_FAILED))
        if known is None:
            session.add(Deployment(version=failed_version, status=STATUS_FAILED, created_at=now))
    if version:
        current = await session.scalar(
            select(Deployment.version).where(Deployment.status == STATUS_OK)
            .order_by(Deployment.id.desc()).limit(1))
        if current != version:
            session.add(Deployment(version=version, title=(title or None) and title[:TITLE_MAX],
                                   status=STATUS_OK, created_at=now))
    await session.flush()
```
В `main()`:
```python
async with sessionmaker() as db, db.begin():
    await record_startup(db, config.app_version, config.app_title, config.failed_version, utcnow())
log.info("Version: %s", config.app_version or "local")
```

## Доставка (планировщик)
На каждом тике: все записи с `notified_at IS NULL` отправить всем пользователям из БД, затем
проставить `notified_at`. На свежей БД пользователей нет до `/start` — записи ждут.
Сетевые ошибки Telegram → выход и повтор на следующем тике; `Forbidden`/`BadRequest` → лог и
пометить как отправленное, чтобы не зациклиться.
```python
async def deliver_deployments(session_factory, bot, now) -> None:
    async with session_factory() as session:
        deployments = await pending_deployments(session)
        if not deployments:
            return
        users = list(await session.scalars(select(User)))
        if not users:
            return  # a fresh DB has no user until /start
        for d in deployments:
            try:
                for user in users:
                    await bot.send_message(user.tg_id, deployment_text(d))
            except (TelegramForbiddenError, TelegramBadRequest):
                log.exception("Dropping deployment notice %s", d.id)
            except _RETRYABLE as exc:
                log.warning("Telegram unavailable (%s); will retry", exc)
                return
            d.notified_at = now
            await session.commit()
```

## Текст (`views.py`)
```python
def deployment_text(d: Deployment, when: str | None = None) -> str:
    """``when``: '2 часа назад', for the history; a fresh notice goes without it."""
    stamp = f" · <i>{when}</i>" if when else ""
    if d.status == STATUS_OK:
        title = f"\n{escape(d.title)}" if d.title else ""
        return f"🔄 Бот обновлён до версии <code>{d.version[:7]}</code>{stamp}{title}"
    return (f"⚠️ Обновление <code>{d.version[:7]}</code> не запустилось{stamp}\n"
            "Бот вернулся на предыдущую версию.")
```
`escape` — `html.escape`: тема коммита может содержать `<`/`&`, а parse_mode HTML.

## История в настройках
Кнопка `settings:updates` → последние 10 записей (`list_deployments`), каждая с относительным
временем `ago(as_utc(d.created_at), now, tz)`, и кнопка «« Настройки».
