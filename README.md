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

## Run The App

This project is currently easiest to run with Docker for services and the app container.

### 1. Start the app and dependencies

```powershell
docker compose up -d --build app postgres redis
```

### 2. Run migrations inside Docker

This repo's current `.env` is Docker-oriented, so run Alembic inside the app container:

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

If you want to run a focused subset:

```powershell
uv run pytest tests/integration/test_documents.py tests/integration/test_sources.py -v
```

## API Surface

Current routers are mounted under `app/api/v1/`:

- `/v1/documents`
- `/v1/sources`
- `/v1/alerts`
- `/v1/scores`
- `/v1/audit`

Useful endpoints include:

- `GET /health`
- `POST /v1/documents/upload`
- `GET /v1/documents`
- `GET /v1/documents/{id}`
- `DELETE /v1/documents/{id}`
- `POST /v1/sources`
- `GET /v1/sources`
- `POST /v1/sources/{id}/sync`

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


