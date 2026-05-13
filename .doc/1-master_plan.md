# Drift Guard - Master Plan

> UPDATED 2026-04-18: Reconciled against the current repository state and updated with a strict 0 Rs execution policy for Phases 7-9.
>
> UPDATED 2026-05-02: Tracked audit run/job APIs, source sync background handoff, and audit report endpoints are implemented on the ARQ worker foundation.
>
> UPDATED 2026-05-13: Phase 8 notifications and the Phase 9 hardening/docs baseline are implemented.

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
- API key protection on documents, sources, alerts, and scores routes
- direct Markdown upload with versioning and soft delete
- GitHub-backed Git source creation, listing, and sync
- Markdown normalization before persistence
- entity extraction for `url`, `dashboard`, `service`, `owner`, `command`, `env_var`, `iam_role`, `helm_chart`, and `cluster`
- evidence collectors for GitHub, HTTP probe, incident.io, and Kubernetes
- drift rule engine with alert persistence and alert APIs
- scoring service with score snapshot persistence
- score APIs for list and document-level retrieval
- local/self-hosted ARQ worker runtime with tracked `AuditJob` lifecycle
- audit job APIs for manual run creation, job listing, and job detail polling
- audit report APIs for global and service-scoped summaries
- Slack webhook, local email sink, and audit completion webhook notifications
- request logging, rate limits, queue capacity guards, GitHub Actions CI, and
  local observability/load-test runbooks
- unit tests for extractors and scoring, plus integration tests for health, documents, sources, alerts, and scores

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

- Phase 4 collectors are implemented for GitHub, HTTP probe, incident.io, and Kubernetes
- collector tests use mocked external responses for reliable local development
- real incident.io and Kubernetes credentials are optional and only required for live evidence checks

## What Is Not Done Yet

The original Phase 0-9 checklist is now implemented at the local MVP level.
Remaining work is production rollout work, not missing planned foundation:

- production deployment policy
- deeper scale/load testing beyond the local nightly-scan helper
- optional frontend or CI-blocking product workflows

`audit` now supports tracked run/job endpoints plus global and service-scoped report endpoints.

## Zero-Rupee Delivery Constraint (Phases 7-9)

Phases 7, 8, and 9 must be implemented with strict 0 Rs recurring spend.

Allowed:

- existing Docker Compose services (app, Postgres, Redis)
- open-source libraries and frameworks
- self-hosted scheduling and worker processes
- free Slack incoming webhook integration
- local/test email sink for notification validation

Not allowed:

- paid managed queue/scheduler services
- paid email providers for this phase
- paid SaaS monitoring dependencies as a requirement

## Recommended Next Step

The next meaningful phase is to move from "evaluate and report" to "orchestrate and operate".

Recommended order:

1. Keep running lint, unit tests, migration checks, and integration smoke tests through CI.
2. Use the Phase 9 observability and load-test runbooks before demos or releases.
3. Decide whether the next product milestone is production deployment, frontend UX, or CI reliability gates.

## Practical MVP Status

### Implemented now

- ingestion
- version tracking
- entity extraction
- evidence collection foundation
- drift rules and alerts APIs
- scoring service and score APIs
- source sync
- tracked audit run and job polling APIs
- background source sync handoff with non-null `audit_job_id`
- global and service-scoped audit report APIs
- free-only notification delivery
- request logging, CI, contributor docs, observability notes, and nightly-scan load testing
- tests for ingestion, alert, and scoring slices

### Current Milestone

The local MVP milestone through Phase 9 is implemented.

## Success Criteria For The Current Milestone

The Phase 0-9 milestone is complete when the repository can:

- trigger a tracked audit run asynchronously
- expose audit job lifecycle endpoints with reliable status transitions
- expose global and service-scoped audit report summaries
- run nightly scan scheduling from local/self-hosted worker runtime
- keep notification and hardening features within the 0 Rs constraint
- run the Phase 9 CI, observability, and load-test checks

The project can now be described as "drift detection, scoring, tracked audit jobs, background source sync, audit reports, notifications, and the local hardening/docs baseline implemented."
