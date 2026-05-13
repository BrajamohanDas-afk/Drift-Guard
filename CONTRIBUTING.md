# Contributing To Drift Guard

Thanks for helping with Drift Guard. Keep changes small, tested, and aligned
with the current API-first backend shape.

## Local Setup

Use Docker for the app dependencies:

```powershell
Copy-Item .env.docker.example .env
docker compose up -d --build app worker postgres redis
docker compose exec app uv run alembic upgrade head
```

For host-side tests on Windows, use the `localhost:5433` database URLs from
`.env.local.example` and make sure integration tests point at a database whose
name contains `test`.

## Before Opening A PR

Run:

```powershell
uv run ruff check app tests
uv run pytest tests/unit -q
```

For database-backed changes, also run:

```powershell
uv run alembic heads
uv run pytest tests/integration/test_audit.py tests/integration/test_notifications.py -q
```

## Development Rules

- Keep `/v1/*` endpoints behind the API key dependency unless the whole auth
  model is changed deliberately.
- Do not log API keys, webhook URLs, bearer tokens, document secrets, or raw
  source config values.
- Keep external integrations optional and read-only.
- Prefer local/self-hosted tooling for Phases 7-9; no paid SaaS dependency is
  required for the planned milestone.
- Add tests close to the behavior you change.

## Migrations

When changing SQLAlchemy models, add an Alembic migration and verify that
`uv run alembic upgrade head` works against a disposable local database.
