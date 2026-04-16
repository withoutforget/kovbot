# Kov (Kov/Kora) — bot + RAG backend

This repository contains:

- `apps/api`: FastAPI backend (RAG Scan/Search + LLM proxy + scenarios)
- `apps/bot`: Telegram bot (aiogram) for scenario UI
- `apps/worker`: background jobs (scheduler + async pipelines)

## Quickstart (dev)

1) Start infra:

```bash
docker compose up -d --build
```

2) Open API docs: `http://localhost:8000/docs`

If `TELEGRAM_BOT_TOKEN` is not set, the `bot` container stays running but does not connect to Telegram.
Create `.env` from `.env.example` to enable the bot and/or configure LLM.

## Production (docker compose)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Tests

```bash
pytest -q
pytest -q tests/e2e
```
