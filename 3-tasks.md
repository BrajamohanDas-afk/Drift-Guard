# Runbook Drift Radar — Tasks

> Ordered by phase. Each task is atomic and independently shippable. Check off as you go.
>
> Current repo status as of 2026-03-12: planning documents exist, but no application scaffold or implementation files are present yet. Leave implementation tasks unchecked until corresponding code, config, tests, or project files exist in the repository.

---

## Phase 0 — Project Bootstrap

- [x] **T-001** Initialize Python project with `pyproject.toml` (Poetry or uv)
- [x] **T-002** Set up FastAPI app skeleton (`app/main.py`, health check endpoint `GET /health`)
- [x] **T-003** Set up Docker Compose with: app, postgres, redis
- [x] **T-004** Configure `pydantic-settings` for env-based config (`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`)
- [x] **T-005** Set up Alembic with initial empty migration
- [x] **T-006** Create `.env.example` file with all required variables
- [x] **T-007** Set up `pytest` with basic test config and a smoke test
- [x] **T-008** Set up pre-commit hooks (ruff, black, mypy)

---

## Phase 1 — Database & Models

- [ ] **T-010** Write SQLAlchemy model: `Source`
- [ ] **T-011** Write SQLAlchemy model: `Document`
- [ ] **T-012** Write SQLAlchemy model: `DocumentVersion`
- [ ] **T-013** Write SQLAlchemy model: `Entity`
- [ ] **T-014** Write SQLAlchemy model: `Alert`
- [ ] **T-015** Write SQLAlchemy model: `RunbookScore`
- [ ] **T-016** Write SQLAlchemy model: `AuditJob`
- [ ] **T-017** Generate and apply Alembic migration for all tables
- [ ] **T-018** Write Pydantic schemas for request/response (Document, Alert, Score, AuditJob)
- [ ] **T-019** Write unit tests for all models (field validation, constraints)

---

## Phase 2 — Document Ingestion

- [ ] **T-020** Implement `POST /v1/documents/upload` — accept Markdown file upload, save to `documents`
- [ ] **T-021** Implement content hashing on upload (SHA-256), skip if content unchanged
- [ ] **T-022** Implement `document_version` creation on every new content hash
- [ ] **T-023** Implement `GET /v1/documents` — list all documents (paginated)
- [ ] **T-024** Implement `GET /v1/documents/{id}` — get single document with latest version
- [ ] **T-025** Implement `DELETE /v1/documents/{id}` — soft delete/archive only, preserving versions and audit history
- [ ] **T-026** Implement Markdown ingestor (`services/ingestion/markdown_ingestor.py`) — strip syntax, extract plain text
- [ ] **T-027** Implement Git ingestor — connect to repo, walk path, pull `.md` files
- [ ] **T-028** Implement `POST /v1/sources` — create source record
- [ ] **T-029** Implement `GET /v1/sources` — list sources (mask credentials in response)
- [ ] **T-030** Implement `POST /v1/sources/{id}/sync` — trigger async sync job, return `202 + audit_job_id`
- [ ] **T-031** Write integration tests for upload and sync endpoints

---

## Phase 3 — Entity Extraction

- [ ] **T-040** Implement URL entity extractor (regex, capture all `http/https` URLs from doc text)
- [ ] **T-040A** Implement dashboard extractor (identify Grafana/Datadog-style dashboard references and persist as `dashboard` entities)
- [ ] **T-041** Implement service name extractor (regex patterns: `kebab-case`, known suffixes like `-api`, `-service`)
- [ ] **T-042** Implement owner extractor (`@username`, `team-name` patterns)
- [ ] **T-043** Implement command extractor (code blocks, `kubectl`, `helm`, `bash` commands)
- [ ] **T-044** Implement env var extractor (`ALL_CAPS_WITH_UNDERSCORES` pattern)
- [ ] **T-045** Implement IAM role extractor (`arn:aws:iam::` pattern)
- [ ] **T-046** Implement Helm chart extractor (`chart@version` pattern)
- [ ] **T-046A** Implement cluster extractor (`prod-us-east-1`, `staging-eu-west-1`, named kube contexts)
- [ ] **T-047** Wire all extractors into unified `EntityExtractor` service
- [ ] **T-048** Persist extracted entities to `entities` table (deduplicate per document)
- [ ] **T-048A** Persist `document_version_id` on every entity row and scope deduplication to a single document version
- [ ] **T-049** Trigger entity extraction automatically after document ingest
- [ ] **T-050** Write unit tests for each extractor with positive + negative cases

---

## Phase 4 — Evidence Collectors

- [ ] **T-060** Implement GitHub evidence collector:
  - Fetch CODEOWNERS file
  - Fetch file tree at given path
  - Check if a file path exists in repo
- [ ] **T-061** Implement HTTP probe collector: check URL, return status code + response time
- [ ] **T-062** Implement PagerDuty collector: list services + escalation policy owners
- [ ] **T-063** Implement Kubernetes collector (basic): list deployments + namespaces across contexts
- [ ] **T-064** Implement `EvidenceStore` — per-audit cache for external lookups and normalized evidence snapshots persisted on alerts
- [ ] **T-064A** Define `EvidenceStore` boundary for MVP — request/audit-scoped in-memory cache that is serialized into `alerts.evidence` on alert creation; no standalone persistence table
- [ ] **T-065** Write unit tests for each collector with mocked HTTP responses

---

## Phase 5 — Drift Rules Engine

- [ ] **T-070** Define `BaseDriftRule` interface (abstract class with `rule_type`, `severity`, `evaluate()`)
- [ ] **T-071** Implement `OwnerMissingRule` — check entity owner against GitHub CODEOWNERS + PagerDuty
- [ ] **T-072** Implement `DashboardDeadRule` — probe URL entity, alert on non-200
- [ ] **T-073** Implement `CommandDeprecatedRule` — check script path in repo file tree
- [ ] **T-074** Implement `HelmVersionStaleRule` — compare doc Helm version vs deployed version
- [ ] **T-075** Implement `DependencyUndocumentedRule` — compare Kubernetes services vs documents table
- [ ] **T-076** Implement `RulesEngine` — orchestrates all rules against all entities, returns alert list
- [ ] **T-077** Implement alert deduplication logic (skip if identical unresolved alert exists)
- [ ] **T-078** Persist new alerts to `alerts` table
- [ ] **T-079** Implement `GET /v1/alerts` — list alerts (filter by severity, service, document, resolved)
- [ ] **T-080** Implement `GET /v1/alerts/{id}` — single alert with full evidence
- [ ] **T-081** Implement `PATCH /v1/alerts/{id}/resolve` — mark resolved
- [ ] **T-082** Write unit tests for each rule — both drift detected and no drift cases

---

## Phase 6 — Scoring

- [ ] **T-090** Implement scoring algorithm in `services/scoring/scorer.py`
- [ ] **T-091** Score deductions: per critical/warning/info alert, stale doc penalty, no-entity penalty
- [ ] **T-092** Persist scores to `runbook_scores` with full `breakdown` JSONB
- [ ] **T-093** Trigger scoring automatically after each document's rule evaluation
- [ ] **T-094** Implement `GET /v1/scores` — list all scores with band labels (paginated)
- [ ] **T-095** Implement `GET /v1/scores/{document_id}` — score + breakdown for one doc
- [ ] **T-096** Write unit tests for scorer with edge cases (all critical, no alerts, no entities)

---

## Phase 7 — Background Jobs & Scheduling

- [ ] **T-100** Set up Celery (or Arq) with Redis broker
- [ ] **T-101** Implement `nightly_scan` task — full pipeline for all connected sources
- [ ] **T-102** Implement `ingest_task` — async wrapper for source sync
- [ ] **T-103** Implement `score_task` — async scorer trigger
- [ ] **T-104** Configure nightly cron schedule (02:00 UTC)
- [ ] **T-105** Implement `AuditJob` lifecycle: `pending` → `running` → `complete` / `partial` / `failed`
- [ ] **T-106** Implement `POST /v1/audit/run` — trigger manual full audit or targeted audit by `document_id`, return `202`
- [ ] **T-107** Implement `GET /v1/audit/jobs` — list audit job history
- [ ] **T-108** Implement `GET /v1/audit/jobs/{id}` — poll single job status
- [ ] **T-109** Implement `GET /v1/audit/report` — latest audit summary JSON
- [ ] **T-110** Implement `GET /v1/audit/service/{service_name}` — findings for one service

---

## Phase 8 — Alerting & Output

- [ ] **T-120** Implement Slack webhook notifier (`services/alerting/slack_notifier.py`)
- [ ] **T-121** Design Slack message format (summary block + alert list with emoji severity)
- [ ] **T-122** Implement email notifier (SMTP or SendGrid) with digest template
- [ ] **T-123** Implement configurable alert routing (which severity goes where)
- [ ] **T-124** Trigger Slack/email digest at end of nightly scan if alerts exist
- [ ] **T-125** Add webhook output to `POST /v1/audit/run` — notify URL on completion
- [ ] **T-126** Write integration test for Slack notifier with mocked webhook

---

## Phase 9 — Hardening & Docs

- [ ] **T-130** Add API key authentication middleware (`X-API-Key` header)
- [ ] **T-131** Add request logging middleware (method, path, status, duration)
- [ ] **T-132** Add rate limiting middleware (per API key)
- [ ] **T-133** Configure Swagger/OpenAPI docs at `/docs` (auto from FastAPI)
- [ ] **T-134** Write `README.md` with: quickstart, env vars, API overview, Docker instructions
- [ ] **T-135** Add `CONTRIBUTING.md` with: branch naming, PR process, test requirements
- [ ] **T-136** Set up GitHub Actions CI: lint → type check → test on every PR
- [ ] **T-137** Add Sentry integration for error tracking (optional but recommended)
- [ ] **T-138** Load test the nightly scan with 100 documents (target: < 5 min)

---

## Backlog (Post-MVP)

- [ ] **B-001** Confluence ingestor (OAuth + export API)
- [ ] **B-002** Notion ingestor (Notion API)
- [ ] **B-003** AWS IAM role existence checker
- [ ] **B-003A** Jira collector for ownership and incident/workflow evidence
- [ ] **B-003B** CI/CD collector for deployed artifact and pipeline evidence
- [ ] **B-004** pgvector integration for semantic doc search
- [ ] **B-005** Multi-workspace / multi-tenant support
- [ ] **B-006** GitHub Actions native action (publish to Marketplace)
- [ ] **B-007** Web dashboard (React) for browsing scores + alerts
- [ ] **B-008** Custom drift rule builder (config-driven, no code)
- [ ] **B-009** "Doc freshness" trend charts per service over time
- [ ] **B-010** Runbook template generator (creates compliant doc scaffolds)
- [ ] **B-011** Weekly digest schedules as a first-class feature (`notification_schedules` table plus API or config-management endpoint)

---

## Task Summary

| Phase | Tasks | Priority |
|---|---|---|
| Bootstrap | T-001 → T-008 | Now |
| DB & Models | T-010 → T-019 | Now |
| Ingestion | T-020 → T-031 | Week 1 |
| Extraction | T-040 → T-050 | Week 2 |
| Evidence | T-060 → T-065 | Week 2–3 |
| Drift Rules | T-070 → T-082 | Week 3–4 |
| Scoring | T-090 → T-096 | Week 4 |
| Jobs | T-100 → T-110 | Week 5 |
| Alerting | T-120 → T-126 | Week 5 |
| Hardening | T-130 → T-138 | Week 6 |
| Backlog | B-001 → B-010 | Post-MVP |
