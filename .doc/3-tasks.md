# Drift Guard - Tasks

> UPDATED 2026-03-30: Task statuses below were reconciled against the current repository. Checkmarks mean the code and tests exist today. Open tasks are still pending or only partially addressed.

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
- [ ] T-032 Move source sync to a real background job and return a non-null `audit_job_id`

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
- [x] T-062 Implement PagerDuty collector
- [x] T-063 Implement Kubernetes collector
- [x] T-064 Implement `EvidenceStore`
- [x] T-065 Write collector unit tests with mocked responses

---

## Phase 5 - Drift Rules Engine

- [ ] T-070 Define `BaseDriftRule` interface
- [ ] T-071 Implement `OwnerMissingRule`
- [ ] T-072 Implement `DashboardDeadRule`
- [ ] T-073 Implement `CommandDeprecatedRule`
- [ ] T-074 Implement `HelmVersionStaleRule`
- [ ] T-075 Implement `DependencyUndocumentedRule`
- [ ] T-076 Implement `RulesEngine`
- [ ] T-077 Implement alert deduplication
- [ ] T-078 Persist generated alerts
- [ ] T-079 Implement `GET /v1/alerts`
- [ ] T-080 Implement `GET /v1/alerts/{id}`
- [ ] T-081 Implement `PATCH /v1/alerts/{id}/resolve`
- [ ] T-082 Write rule tests

---

## Phase 6 - Scoring

- [ ] T-090 Implement scoring algorithm
- [ ] T-091 Add score deductions and breakdown logic
- [ ] T-092 Persist scores to `runbook_scores`
- [ ] T-093 Trigger scoring after rule evaluation
- [ ] T-094 Implement `GET /v1/scores`
- [ ] T-095 Implement `GET /v1/scores/{document_id}`
- [ ] T-096 Write scorer tests

---

## Phase 7 - Background Jobs And Scheduling

- [ ] T-100 Set up background worker runtime
- [ ] T-101 Implement `nightly_scan`
- [ ] T-102 Implement async `ingest_task`
- [ ] T-103 Implement async `score_task`
- [ ] T-104 Configure nightly schedule
- [ ] T-105 Implement `AuditJob` lifecycle
- [ ] T-106 Implement `POST /v1/audit/run`
- [ ] T-107 Implement `GET /v1/audit/jobs`
- [ ] T-108 Implement `GET /v1/audit/jobs/{id}`
- [ ] T-109 Implement `GET /v1/audit/report`
- [ ] T-110 Implement `GET /v1/audit/service/{service_name}`

---

## Phase 8 - Alerting And Output

- [ ] T-120 Implement Slack webhook notifier
- [ ] T-121 Define Slack message payload format
- [ ] T-122 Implement email notifier
- [ ] T-123 Implement configurable alert routing
- [ ] T-124 Trigger notifier delivery at end of audit
- [ ] T-125 Add completion webhook support for manual audit runs
- [ ] T-126 Write notifier tests

---

## Phase 9 - Hardening And Docs

- [x] T-130 Add API key enforcement for the active document/source endpoints
- [ ] T-131 Add request logging middleware
- [ ] T-132 Add rate limiting middleware
- [x] T-133 Keep FastAPI OpenAPI docs enabled at `/docs`
- [x] T-134 Maintain a current `README.md`
- [ ] T-135 Add `CONTRIBUTING.md`
- [ ] T-136 Set up GitHub Actions CI
- [ ] T-137 Add Sentry or equivalent error monitoring
- [ ] T-138 Load test the nightly scan

---

## Current Recommended Next Slice

- [ ] N-001 Add the first real evidence collector
- [ ] N-002 Implement the first rule that can generate an alert
- [ ] N-003 Persist and expose alerts through `/v1/alerts`
- [ ] N-004 Add tests for the first end-to-end drift detection path

---

## Status Summary

Completed foundation:

- project bootstrap
- data model
- upload ingestion
- Git sync
- entity extraction
- test coverage for the implemented ingestion path

Current gap between plan and product:

- the project can ingest and extract, but it still cannot evaluate drift or report it through alerts, scores, or audits
