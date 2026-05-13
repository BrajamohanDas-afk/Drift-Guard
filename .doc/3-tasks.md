# Drift Guard - Tasks

> UPDATED 2026-03-30: Task statuses below were reconciled against the current repository. Checkmarks mean work is implemented and verified (tests where applicable). Open tasks are still pending or only partially addressed.
>
> UPDATED 2026-04-18: Phases 7-9 are now constrained to strict 0 Rs recurring spend (no paid dependencies required to complete these phases).
>
> UPDATED 2026-05-02: Tracked audit run/job APIs, source sync background handoff, and audit report endpoints are implemented and verified. Full integration suite passes locally against Docker/Postgres when the Windows-side test process uses `localhost:5433`.
>
> UPDATED 2026-05-09: Phase 8 notification delivery is implemented with free-only Slack webhook, local email sink, configurable routing, audit completion webhook support, durable delivery logs, and focused tests.
>
> UPDATED 2026-05-13: Phase 9 hardening/docs baseline is implemented with request logging, existing rate limits, contributing docs, GitHub Actions CI, free/local observability guidance, and a nightly-scan load-test helper.

---

## Phase 0 - Project Bootstrap

- [x] T-001 Initialize Python project with `pyproject.toml`
- [x] T-002 Set up FastAPI app skeleton with `GET /health`
- [x] T-003 Set up Docker Compose with app, Postgres, and Redis
- [x] T-004 Configure `pydantic-settings` for env-based config
- [x] T-005 Set up Alembic
- [x] T-006 Create `.env.example`
- [x] T-007 Set up `pytest` and basic integration coverage
- [x] T-008 Set up pre-commit hooks

---

## Phase 1 - Database And Models

- [x] T-010 Write SQLAlchemy model: `Source`
- [x] T-011 Write SQLAlchemy model: `Document`
- [x] T-012 Write SQLAlchemy model: `DocumentVersion`
- [x] T-013 Write SQLAlchemy model: `Entity`
- [x] T-014 Write SQLAlchemy model: `Alert`
- [x] T-015 Write SQLAlchemy model: `RunbookScore`
- [x] T-016 Write SQLAlchemy model: `AuditJob`
- [x] T-017 Generate Alembic migration for core tables
- [x] T-018 Write Pydantic schemas for implemented resources
- [x] T-019 Add schema/model validation tests

---

## Phase 2 - Document Ingestion

- [x] T-020 Implement `POST /v1/documents/upload`
- [x] T-021 Implement content hashing on upload
- [x] T-022 Create `document_version` records on content change
- [x] T-023 Implement `GET /v1/documents`
- [x] T-024 Implement `GET /v1/documents/{id}`
- [x] T-025 Implement soft delete for documents
- [x] T-026 Implement Markdown normalization
- [x] T-027 Implement recursive Git Markdown ingestion
- [x] T-028 Implement `POST /v1/sources`
- [x] T-029 Implement `GET /v1/sources`
- [x] T-030 Implement source sync endpoint and document upsert flow
- [x] T-031 Write integration tests for upload and sync behavior
- [x] T-032 Move source sync to a real background job and return a non-null `audit_job_id`

---

## Phase 3 - Entity Extraction

- [x] T-040 Implement URL extractor
- [x] T-040A Implement dashboard extractor
- [x] T-041 Implement service extractor
- [x] T-042 Implement owner extractor
- [x] T-043 Implement command extractor
- [x] T-044 Implement env var extractor
- [x] T-045 Implement IAM role extractor
- [x] T-046 Implement Helm chart extractor
- [x] T-046A Implement cluster extractor
- [x] T-047 Wire extractors into unified `EntityExtractor`
- [x] T-048 Persist extracted entities
- [x] T-048A Persist `document_version_id` on entity rows
- [x] T-049 Trigger extraction automatically after ingest and sync
- [x] T-050 Write unit tests for each extractor with positive and negative cases

---

## Phase 4 - Evidence Collectors

- [x] T-060 Implement GitHub evidence collector
- [x] T-061 Implement HTTP probe collector
- [x] T-062 Implement incident.io collector
- [x] T-063 Implement Kubernetes collector
- [x] T-064 Implement `EvidenceStore`
- [x] T-065 Write collector unit tests with mocked responses

---

## Phase 5 - Drift Rules Engine

- [x] T-070 Define `BaseDriftRule` interface
- [x] T-071 Implement `OwnerMissingRule`
- [x] T-072 Implement `DashboardDeadRule`
- [x] T-073 Implement `CommandDeprecatedRule`
- [x] T-074 Implement `HelmVersionStaleRule`
- [x] T-075 Implement `DependencyUndocumentedRule`
- [x] T-076 Implement `RulesEngine`
- [x] T-077 Implement alert deduplication
- [x] T-078 Persist generated alerts
- [x] T-079 Implement `GET /v1/alerts`
- [x] T-080 Implement `GET /v1/alerts/{id}`
- [x] T-081 Implement `PATCH /v1/alerts/{id}/resolve`
- [x] T-082 Write rule tests

---

## Phase 6 - Scoring

- [x] T-090 Implement scoring algorithm
- [x] T-091 Add score deductions and breakdown logic
- [x] T-092 Persist scores to `runbook_scores`
- [x] T-093 Trigger scoring after rule evaluation
- [x] T-094 Implement `GET /v1/scores`
- [x] T-095 Implement `GET /v1/scores/{document_id}`
- [x] T-096 Write scorer tests

---

## Phase 7 - Background Jobs And Scheduling

- Constraint: use local/self-hosted worker runtime with existing Redis and Docker services only.

- [x] T-100 Set up background worker runtime
- [x] T-101 Implement `nightly_scan`
- [x] T-102 Implement async `ingest_task`
- [x] T-103 Implement async `score_task`
- [x] T-104 Configure nightly schedule
- [x] T-105 Implement `AuditJob` lifecycle
- [x] T-106 Implement `POST /v1/audit/run`
- [x] T-107 Implement `GET /v1/audit/jobs`
- [x] T-108 Implement `GET /v1/audit/jobs/{id}`
- [x] T-109 Implement `GET /v1/audit/report`
- [x] T-110 Implement `GET /v1/audit/service/{service_name}`

---

## Phase 8 - Alerting And Output

- Constraint: free-only delivery in this phase (Slack webhook + local/test email sink).

- [x] T-120 Implement Slack webhook notifier
- [x] T-121 Define Slack message payload format
- [x] T-122 Implement email notifier with local/test sink mode (no paid provider required)
- [x] T-123 Implement configurable alert routing
- [x] T-124 Trigger notifier delivery at end of audit
- [x] T-125 Add completion webhook support for manual audit runs
- [x] T-126 Write notifier tests

---

## Phase 9 - Hardening And Docs

- Constraint: free/local/self-hosted implementation only; no paid SaaS or paid CI required.

- [x] T-130 Add API key enforcement for the active document/source endpoints
- [x] T-131 Add request logging middleware
- [x] T-132 Add rate limiting middleware
- [x] T-133 Keep FastAPI OpenAPI docs enabled at `/docs`
- [x] T-134 Maintain a current `README.md`
- [x] T-135 Add `CONTRIBUTING.md`
- [x] T-136 Set up GitHub Actions CI
- [x] T-137 Add open-source/self-hosted equivalent error monitoring (no paid SaaS requirement)
- [x] T-138 Load test the nightly scan

---

## Current Recommended Next Slice

- [x] N-009 Implement remaining worker task wiring (`T-103`)
- [x] N-010 Implement tracked audit run job APIs only (`T-105` to `T-108`)
- [x] N-011 Move sync to background execution with non-null `audit_job_id` (`T-032`)
- [x] N-012 Run and finalize integration tests for audit and job flows
- [x] N-013 Add audit reporting endpoints (`T-109` and `T-110`)
- [x] N-014 Implement Phase 8 notification delivery (`T-120` to `T-126`)
- [x] N-015 Complete Phase 9 hardening/docs baseline (`T-131` to `T-138`)

---

## Status Summary

Completed foundation:

- project bootstrap
- data model
- upload ingestion
- Git sync
- entity extraction
- evidence collectors and evidence store
- drift rules engine and alert APIs
- scoring service and score APIs
- local/self-hosted worker runtime, tracked audit job APIs, and audit report APIs
- free-only notification delivery with Slack webhook, local email sink, and audit completion webhook support
- request logging, rate limiting, queue capacity guards, CI, contributor docs, local observability guidance, and nightly-scan load-test tooling
- test coverage for ingestion, alerts, and scoring slices

Current gap between plan and product:

- the project can ingest, extract, report alerts, expose scores, enqueue tracked audit runs, poll audit jobs, return global/service audit summaries, and deliver configured notifications
- remaining work is now outside the original Phase 0-9 checklist: production deployment policy, deeper scale testing, and any future frontend or CI-gating product features
