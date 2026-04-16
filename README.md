# Kov — Telegram bot + RAG backend

В репозитории:

- `apps/api`: FastAPI API (RAG scan/search, LLM proxy)
- `apps/bot`: Telegram bot (aiogram)
- `apps/worker`: фоновые задачи (напоминания)
- `docker-compose.yml`: dev-стек
- `docker-compose.prod.yml`: прод-оверлей (изоляция + nginx + бекапы)

## Быстрый старт (dev)

1) Создай `.env`:

```bash
cp .env.example .env
```

2) Подними инфраструктуру:

```bash
docker compose up -d --build
```

3) Открой:

- API docs: `http://localhost:8000/docs`
- Админка (SSR): `http://localhost:8000/admin/`

Если `TELEGRAM_BOT_TOKEN` не задан, контейнер `bot` не подключится к Telegram (это нормально для dev).

## Прод (docker compose + nginx)

В прод-режиме наружу торчит только `nginx`:

- `:80` — админка (`/admin/`) под basic-auth
- `:8443` — (опционально) весь API под basic-auth
- `postgres/qdrant/minio/api/worker/bot` — только во внутренней docker-сети

Запуск:

```bash
cp .env.example .env
# обязательно: поставь сильный пароль
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Важно:
- `ADMIN_PASSWORD` обязателен для `docker-compose.prod.yml`.
- Для API снаружи используйте `http://<host>:8443/` (также под basic-auth).
- Бот ходит в API по внутреннему адресу `http://api:8000` и не требует авторизации.

## Бекапы (каждые 2 часа, хранить 36 часов)

Автобекапы включены в прод-оверлее сервисом `backup`:

- интервал: `BACKUP_INTERVAL_MINUTES=120`
- хранение: `BACKUP_KEEP_HOURS=36`
- локально: docker volume `backups_data` (в контейнере: `/backups`)
- опционально: загрузка в отдельное S3-хранилище через `BACKUP_S3_*`

Ручной бекап (one-shot):

```bash
./scripts/backup_now.sh
```

Ручное восстановление (архив должен лежать в `/backups` volume, можно передать только имя файла):

```bash
./scripts/restore_from_backup.sh backup_YYYYmmddTHHMMSSZ.tar.gz
```

Что внутри архива:
- `postgres.dump` (pg_dump custom format)
- `qdrant_<collection>_<snapshot>` (snapshot коллекции)
- `s3_bucket/` (если `BACKUP_INCLUDE_S3_DATA=1`)

## Админка (SSR)

Доступна по `/admin/` и умеет:

- смотреть документы/чанки в RAG
- загружать PDF и запускать обработку
- выполнять Qdrant search с параметрами и JSON-фильтром
- выполнять RAG поиск (answer/debug) с параметрами retrieval и overrides LLM
- смотреть юзеров и агрегаты токенов (IN/OUT по дням)
- экспортировать детальный отчёт по юзеру (JSON)

## Статистика токенов

Трекинг токенов ведётся по RAG запросам (включая streaming). Хранится:

- события: `token_usage_events`
- агрегаты по дням: `user_token_usage_day`

Telegram username сохраняется при `POST /users/ensure` (бот отправляет `telegram_username`).

## Проверка на утечки секретов

Скан по трекаемым файлам (уважает `.gitignore`):

```bash
./scripts/scan_secrets.sh
```

## Тесты

```bash
pytest -q
pytest -q tests/e2e
```
