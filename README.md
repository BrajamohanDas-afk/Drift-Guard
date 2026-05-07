# Drift Guard

Drift Guard is a FastAPI backend service that detects when operational documentation no longer matches real system state.

It is built around one question:

> Can this runbook still be trusted right now?

## The Problem

Runbooks, onboarding notes, and operational docs go stale quickly.

Typical drift looks like:

- service names change
- owners move teams
- dashboard links break
- commands become outdated
- IAM roles or environment variables change
- production services exist without reliable documentation

When drift is not caught early, incidents take longer, operators lose trust in docs, and routine operations become harder than they should be.

## How Drift Guard Helps

Drift Guard helps teams keep documentation aligned with reality by:

- ingesting runbooks from direct Markdown upload and Git-backed sources
- versioning documents instead of overwriting them
- extracting machine-checkable entities such as services, owners, commands, URLs, IAM roles, dashboards, Helm charts, and clusters
- storing extracted entities against the exact document version they came from
- creating a foundation for drift alerts, audit workflows, and reliability scoring

## Current Capabilities

The current repository includes:

- FastAPI application setup
- SQLAlchemy models and Alembic migrations
- document upload flow
- Git source sync
- Markdown normalization
- entity extraction pipeline
- drift rules plus alert persistence APIs
- alert list/detail/resolve APIs
- scoring APIs with deleted-document filtering
- audit job APIs and audit report summaries
- ARQ worker tasks for source sync, audit runs, scoring, and nightly scans
- API-key auth for `/v1/*` routes
- rate limits for heavy endpoints and worker queue capacity guards
- integration and unit tests
- Docker Compose for local Postgres and Redis

## Core Concepts

### Documents And Versions

Documents are metadata records. Content history lives in `document_versions`.

That separation matters because:

- every scan should be auditable
- extracted entities must point to the exact content version they came from
- direct uploads remain source-less documents
- Git-backed documents are identified by `source_id + path`

### Entities

Extracted entity types currently include:

- `service`
- `owner`
- `url`
- `dashboard`
- `command`
- `env_var`
- `iam_role`
- `helm_chart`
- `cluster`
- `dependency`

## Run The App

This project is currently easiest to run with Docker for services and the app container.

Copy the Docker example env first:

```powershell
Copy-Item .env.docker.example .env
```

Replace `SECRET_KEY`, `API_KEY`, `REDIS_PASSWORD`, and any shared-environment
tokens before running outside your local machine. Known placeholder values such
as `change-me` are rejected at startup.

### 1. Start the app and dependencies

```powershell
docker compose up -d --build app postgres redis
```

### 2. Run migrations inside Docker

When using `.env.docker.example`, run Alembic inside the app container:

```powershell
docker compose exec app uv run alembic upgrade head
```

### 3. Check the health endpoint

```powershell
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Run Tests

Current test workflow from the local shell:

```powershell
uv run pytest -v
```

Notes:

- Pure unit tests under `tests/unit` can run without Docker services.
- Integration tests under `tests/integration` require Postgres (Docker recommended).
- Host-side commands should copy `.env.local.example` to `.env`, or set
  `DATABASE_URL`/`ALEMBIC_DATABASE_URL` to the `localhost:5433` values shown
  there.
- The integration fixture refuses to truncate a database unless the database name
  contains `test`.
- Host-side integration runs should point `DATABASE_URL` at a disposable test
  database, for example the `driftguard_test` URLs shown in `.env.local.example`.

If you want to run a focused subset:

```powershell
uv run pytest tests/integration/test_documents.py tests/integration/test_sources.py -v
```

## Configuration Notes

Phase 4 evidence collectors support optional external integrations:

- `GITHUB_TOKEN` for GitHub evidence collection
- `INCIDENTIO_API_TOKEN` for incident.io evidence collection
- `INCIDENTIO_CATALOG_TYPE_ID` to scope incident.io catalog lookups
- `KUBERNETES_API_URL` and `KUBERNETES_BEARER_TOKEN` for Kubernetes evidence collection

Important behavior:

- `DATABASE_URL` uses `postgres:5432` inside Docker and `localhost:5433` from
  the host.
- Redis requires a password in Docker Compose. The example files use a local-only
  password and bind Redis/Postgres to `127.0.0.1`.
- `SECRET_KEY` and `API_KEY` must be non-placeholder values.
- `/docs`, `/redoc`, and `/openapi.json` are enabled by default for local
  development. Set `PUBLIC_API_DOCS_ENABLED=false` in production.
- incident.io and Kubernetes tokens are optional for local development.
- If `INCIDENTIO_API_TOKEN` is not set, the collector returns a structured
  "not configured" evidence error instead of crashing.
- Unit tests use mocked external API responses, so local test runs do not require
  live incident.io or Kubernetes credentials.

## API Surface

Current routers are mounted under `app/api/v1/`:

- `/v1/documents`
- `/v1/sources`
- `/v1/alerts`
- `/v1/scores`
- `/v1/audit`

Authentication:

- All `/v1/*` routes require the `x-api-key` header.
- `GET /health` remains public for local health checks.

Status notes:

- `/v1/documents`, `/v1/sources`, `/v1/alerts`, `/v1/scores`, and `/v1/audit`
  are implemented.
- Source sync and audit run endpoints enqueue worker jobs through Redis/ARQ.
- Audit runs sync sources, collect supported evidence, evaluate drift rules,
  persist/reconcile alerts, refresh scores, and update audit job counters.
- Heavy endpoints are rate-limited per API key and worker enqueue checks queue
  depth before accepting new work.

Useful endpoints include:

- `GET /health`
- `POST /v1/documents/upload`
- `GET /v1/documents`
- `GET /v1/documents/{id}`
- `DELETE /v1/documents/{id}`
- `POST /v1/sources`
- `GET /v1/sources`
- `POST /v1/sources/{id}/sync`
- `GET /v1/alerts`
- `GET /v1/alerts/{id}`
- `PATCH /v1/alerts/{id}/resolve`
- `GET /v1/scores`
- `GET /v1/scores/{document_id}`
- `POST /v1/audit/run`
- `GET /v1/audit/jobs`
- `GET /v1/audit/jobs/{audit_job_id}`
- `GET /v1/audit/report`
- `GET /v1/audit/service/{service_name}`

Example authenticated request:

```powershell
curl -H "x-api-key: <your-api-key>" http://localhost:8000/v1/documents
```

## Worker Notes

The app uses Redis and ARQ for asynchronous work:

- `ingest_task` syncs Git-backed sources and persists document versions.
- `audit_run_task` syncs sources, runs drift detection, reconciles alerts, and
  refreshes scores.
- `score_task` refreshes a document score snapshot.
- `nightly_scan` enqueues source sync jobs on a cron schedule when enabled.

The API returns `202` for queued source sync and audit run requests. If Redis is
unavailable or the queue is over the configured capacity, the API marks the audit
job failed and returns a service error.

## Tech Stack

- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- asyncpg
- psycopg2
- Pydantic Settings
- PyGithub
- pytest
- Docker Compose
