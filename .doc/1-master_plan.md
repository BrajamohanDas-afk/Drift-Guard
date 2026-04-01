# Drift Guard - Master Plan

> UPDATED 2026-03-30: Reconciled against the current repository state. This file now reflects what is implemented today, what is still missing, and what should be built next.

## Vision

Drift Guard is a backend-first documentation validity engine that checks whether runbooks, SOPs, onboarding guides, and recovery docs still match reality.

The long-term goal is still the same:

- ingest operational docs from multiple sources
- extract machine-checkable entities from those docs
- compare them against live system evidence
- score reliability
- surface drift before it hurts an incident response

## Current Repo Snapshot

The repository is no longer in planning-only state. The current codebase already includes:

- FastAPI application bootstrap with `/health`
- PostgreSQL-backed SQLAlchemy models and Alembic migrations
- API key protection on the active document and source routes
- direct Markdown upload with versioning and soft delete
- GitHub-backed Git source creation, listing, and sync
- Markdown normalization before persistence
- entity extraction for `url`, `dashboard`, `service`, `owner`, `command`, `env_var`, `iam_role`, `helm_chart`, and `cluster`
- evidence collectors for GitHub, HTTP probe, PagerDuty, and Kubernetes
- unit tests for extractors and integration tests for health, documents, and source sync

## What Is Done

### Foundation

- project scaffold is in place
- local Docker services are configured for app, Postgres, and Redis
- settings are loaded from environment variables
- pre-commit, pytest, ruff, and mypy are configured

### Data Model

- `sources`, `documents`, `document_versions`, `entities`, `alerts`, `runbook_scores`, and `audit_jobs` models exist
- document versioning is implemented
- entities are tied to `document_version_id`
- source-backed documents use `source_id + path` as the stable identity
- soft delete is implemented for documents

### Ingestion

- `POST /v1/documents/upload` works
- duplicate uploads with unchanged content do not create a new version
- changed uploads create a new `document_version`
- `POST /v1/sources` works for Git sources
- `GET /v1/sources` works
- `POST /v1/sources/{id}/sync` pulls Markdown files from GitHub and upserts them

### Extraction

- extraction modules exist and are wired into ingestion
- extraction runs automatically after upload and Git sync
- extractor coverage is backed by unit tests

### Evidence Collection Foundation

- Phase 4 collectors are implemented for GitHub, HTTP probe, PagerDuty, and Kubernetes
- collector tests use mocked external responses for reliable local development
- real PagerDuty and Kubernetes credentials are optional and only required for live evidence checks

## What Is Not Done Yet

These planned product areas are still mostly unimplemented:

- drift rules engine
- alert creation and alert APIs
- scoring service and score APIs
- audit execution APIs and real `AuditJob` lifecycle
- background workers and scheduling
- Slack/email/webhook notification delivery
- rate limiting, request logging, CI pipeline, and other hardening work

The `alerts`, `scores`, and `audit` routers exist only as placeholders today.

## Recommended Next Step

The next meaningful phase is to move from "ingest and extract" to "evaluate and report".

Recommended order:

1. Implement the rules engine plus alert persistence and alert endpoints.
2. Add scoring and expose `GET /v1/scores`.
3. Convert source sync and audit execution into tracked background jobs backed by `AuditJob`.
4. Add notification delivery only after alerts and scoring are trustworthy.

## Practical MVP Status

### Implemented now

- ingestion
- version tracking
- entity extraction
- evidence collection foundation
- source sync
- tests for the implemented ingestion path

### Next milestone

"First real drift detection"

That means Drift Guard should be able to:

- collect evidence from at least one live source
- evaluate at least one drift rule end-to-end
- persist alerts
- let users query those alerts through the API

## Success Criteria For The Next Milestone

The next milestone should only be considered complete when the repository can:

- sync documents from a Git source
- extract entities from those documents
- run at least one real rule against collected evidence
- persist generated alerts
- expose alert results through tested API endpoints

Until that exists, the project should be described as "document ingestion and extraction foundation complete" rather than "drift detection complete".
