# Runbook Drift Radar

Runbook Drift Radar is a backend-first service for detecting when operational documentation no longer matches real system state.

It is designed to answer a simple question:

> Can this runbook still be trusted right now?

The service ingests runbooks, extracts structured entities from them, compares those entities against live evidence from connected systems, generates drift alerts, and computes a reliability score for each document.

## What It Will Do

In the MVP, Drift Radar is intended to:

- ingest runbooks from Git repositories and direct Markdown upload
- version every document instead of mutating content in place
- extract entities such as services, owners, dashboard URLs, commands, environment variables, IAM roles, Helm charts, and clusters
- collect evidence from GitHub, Kubernetes, PagerDuty, and HTTP probes
- detect drift through explicit rule checks
- assign a 0-100 reliability score to each document
- expose the results through a REST API
- send notifications through Slack, email, or webhook when drift is found

## Why This Exists

Runbooks are usually written during incidents, migrations, or onboarding, then slowly become inaccurate.

Typical drift looks like:

- service names change
- owners move teams
- dashboards are deleted
- scripts are renamed
- Helm versions change
- new production services exist with no runbook at all

Drift Radar is meant to catch those failures before they matter during an incident.

## How The Program Works

The intended runtime flow is:

1. A document is uploaded or synced from a source.
2. The raw Markdown is normalized and stored as a new `document_version`.
3. The extraction pipeline parses the document and persists entities tied to that exact version.
4. Evidence collectors fetch current state from connected systems.
5. Drift rules evaluate entities against the collected evidence.
6. Alerts are created for confirmed mismatches.
7. The scoring service calculates a reliability score using alert severity, stale-document penalties, and missing-entity penalties.
8. Results are exposed through the API and optionally sent through notification channels.

## Core Concepts

### Documents and Versions

Documents are metadata records. Actual content history lives in `document_versions`.

That separation matters because:

- every scan should be auditable
- extracted entities must point to the exact content version they came from
- preview or CI-scanned documents may differ from the latest canonical version

### Entities

Entities are the structured facts extracted from docs. Examples:

- `service`
- `owner`
- `url`
- `dashboard`
- `command`
- `env_var`
- `iam_role`
- `helm_chart`
- `cluster`

### Evidence

Evidence is the live data used to justify an alert. For MVP, the `EvidenceStore` is intended to be a per-audit in-memory cache whose normalized snapshots are serialized into `alerts.evidence`.

### Alerts

Alerts represent drift or documentation quality problems, such as:

- owner referenced in a doc no longer exists in CODEOWNERS or PagerDuty
- dashboard URL returns a failure
- command in the doc points to a missing script
- deployed service has no runbook

### Scores

Each document gets a reliability score from 0 to 100.

Current scoring intent:

- critical alerts deduct `20` each, up to `60`
- warning alerts deduct `8` each, up to `24`
- info alerts deduct `2` each, up to `6`
- no extracted entities deducts `30`
- document older than 180 days deducts `10`

Score bands:

- `80-100`: Healthy
- `60-79`: Degraded
- `40-59`: Unreliable
- `0-39`: Critical

## MVP API Surface

Planned MVP endpoints include:

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
- `GET /v1/audit/jobs/{id}`
- `GET /v1/audit/report`
- `GET /v1/audit/service/{service_name}`

MVP boundary:

- `GET /v1/audit/report` is JSON-only in MVP
- scheduled weekly digests are post-MVP unless promoted to a first-class config model and API

## Planned Architecture

The project is intended to grow into a structure like this:

```text
app/
  main.py
  config.py
  database.py
  models/
  schemas/
  api/v1/
  services/
    ingestion/
    extraction/
    drift/
    evidence/
    scoring/
    alerting/
  workers/
  utils/
tests/
alembic/
```

Primary subsystems:

- ingestion service
- entity extraction service
- drift rules engine
- evidence store
- scoring service
- alerting service
- REST API
- background workers

## Tech Stack

The current plan uses:

- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- httpx
- Pydantic
- Arq or Celery for background work
- pytest for testing

The current `pyproject.toml` already includes the initial dependency direction.

## Current Repository Status

This repository is still in the early scaffold stage.

What exists now:

- planning documents
- a minimal `pyproject.toml`
- a placeholder `main.py`
- an empty `README.md` that is now being filled in

What does not exist yet:

- FastAPI application structure
- database models
- API routers
- migrations
- tests
- worker setup
- Docker and environment configuration

So this README describes the intended system design and build direction, not a fully implemented service.

## Project Roadmap

### Phase 0: Bootstrap

- initialize Python project
- add FastAPI app skeleton
- add config management
- add Alembic
- add pytest
- add Docker Compose

### Phase 1: Database and Models

- define `Source`
- define `Document`
- define `DocumentVersion`
- define `Entity`
- define `Alert`
- define `RunbookScore`
- define `AuditJob`

### Phase 2: Ingestion

- upload Markdown documents
- support Git source sync
- create new `document_version` rows on content change

### Phase 3: Extraction

- parse URLs
- parse services
- parse owners
- parse commands
- parse env vars
- parse IAM roles
- parse dashboards
- parse clusters

### Phase 4: Evidence Collection

- GitHub collector
- HTTP probe collector
- PagerDuty collector
- Kubernetes collector

### Phase 5: Drift Detection

- owner missing
- dashboard dead
- command deprecated
- Helm version stale
- dependency undocumented

### Phase 6: Scoring

- calculate reliability score
- store score breakdown

### Phase 7: Jobs and Audits

- nightly scan
- manual audit trigger
- audit job lifecycle

### Phase 8: Notifications

- Slack
- email
- webhook completion callback

### Phase 9: Hardening

- API key auth
- logging
- rate limiting
- CI
- API docs

## Getting Started Right Now

The repo is not runnable as the full planned service yet, but the current local Python scaffold can be used as a starting point.

Basic commands:

```powershell
uv sync
uv run python .\main.py
```

That currently runs the placeholder entrypoint only.

If you are starting implementation, the correct next step is to work through the checklist in [3-tasks.md](./3-tasks.md), beginning with:

- `T-001` through `T-008`
- then `T-010` through `T-019`
- then `T-020` through `T-031`

## Source Documents

The project definition currently lives in:

- [1-master_plan.md](./1-master_plan.md)
- [2-implementation_plan.md](./2-implementation_plan.md)
- [3-tasks.md](./3-tasks.md)
- [4-design_guidelines.md](./4-design_guidelines.md)
- [5-user_journey.md](./5-user_journey.md)

If those files change, this README should be kept aligned with them.
