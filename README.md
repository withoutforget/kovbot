# Kov (Kov/Kora) — bot + RAG backend

This repository contains:

- `apps/api`: FastAPI backend (RAG Scan/Search + LLM proxy + scenarios)
- `apps/bot`: Telegram bot (aiogram) for scenario UI
- `apps/worker`: background jobs (scheduler + async pipelines)

## Quickstart (dev)

1) Create `.env` from `.env.example`
2) Start infra:

```bash
docker compose up -d --build
```

3) Open API docs: `http://localhost:8000/docs`

## Tests

```bash
pytest -q
pytest -q tests/e2e
```

