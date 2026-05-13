# Drift Guard - Implementation Plan

> UPDATED 2026-04-18: Rewritten to match the current codebase and strict 0 Rs execution policy for Phases 7-9.
>
> UPDATED 2026-05-02: Audit run/job endpoints, source sync background handoff, and audit report endpoints are implemented on top of the ARQ worker runtime.
>
> UPDATED 2026-05-13: Phase 8 notifications and the Phase 9 hardening/docs baseline are implemented.

## Current Architecture

The repository already has the ingestion foundation in place.

### Present folder shape

```text
Drift-Guard/
|-- app/
|   |-- api/v1/
|   |   |-- audit.py          # run, job tracking, and reports implemented
|   |   |-- alerts.py         # implemented
|   |   |-- documents.py      # implemented
|   |   |-- scores.py         # implemented
|   |   `-- sources.py        # implemented
|   |-- config.py
|   |-- database.py
|   |-- dependencies/auth.py
|   |-- models/
|   |-- schemas/
|   |-- services/
|   |   |-- audit/            # audit job lifecycle + report summaries
|   |   |-- extraction/       # implemented extractors
|   |   |-- ingestion/        # implemented upload + git ingestion helpers
|   |   |-- alerting/         # implemented notification delivery services
|   |   |-- drift/            # implemented rules + alert service
|   |   |-- evidence/         # implemented collectors + store
|   |   `-- scoring/          # implemented scoring service
|   `-- workers/              # ARQ worker runtime + task queue
|-- alembic/
|-- tests/
|   |-- integration/
|   `-- unit/
|-- .doc/
|-- docker-compose.yml
|-- pyproject.toml
`-- README.md
```

## Implemented API Surface

### Working today

- `GET /health`
- `POST /v1/documents/upload`
- `GET /v1/documents`
- `GET /v1/documents/{document_id}`
- `DELETE /v1/documents/{document_id}`
- `POST /v1/sources`
- `GET /v1/sources`
- `POST /v1/sources/{source_id}/sync`
- `GET /v1/alerts`
- `GET /v1/alerts/{alert_id}`
- `PATCH /v1/alerts/{alert_id}/resolve`
- `GET /v1/scores`
- `GET /v1/scores/{document_id}`
- `POST /v1/audit/run`
- `GET /v1/audit/jobs`
- `GET /v1/audit/jobs/{audit_job_id}`
- `GET /v1/audit/report`
- `GET /v1/audit/service/{service_name}`

## Current Data Flow

### Direct upload flow

1. Validate API key.
2. Read uploaded Markdown.
3. Reject invalid UTF-8 or oversized payloads.
4. Find existing source-less document by filename.
5. Reuse the document if the content hash is unchanged.
6. Create a new `document_version` if content changed.
7. Normalize Markdown content.
8. Extract entities.
9. Persist entities against the exact `document_version_id`.

### Git sync flow

1. Validate API key.
2. Load a Git source.
3. Validate sync prerequisites (`git` source type, `repo_url`, configured `GITHUB_TOKEN`).
4. Create a pending `AuditJob`.
5. Enqueue `ingest_task` through ARQ/Redis and return `202` with non-null `audit_job_id`.
6. Worker uses `GitIngestor` to recursively fetch Markdown files from GitHub.
7. Upsert each file using `source_id + path` as identity.
8. Reuse version history when content is unchanged.
9. Update `last_synced_at` and mark the audit job completed or failed.

### Audit report flow

1. Validate API key.
2. For `GET /v1/audit/report`, summarize active documents, unresolved alerts, the latest audit job, and latest per-document score snapshots.
3. For `GET /v1/audit/service/{service_name}`, restrict the same summary to documents whose explicit `service_name` or latest extracted `service` entity matches.
4. Return `404` for unknown services and keep deleted documents out of document-backed counts.

## What The Codebase Is Ready For Next

The next implementation phase should build on top of the current ingestion pipeline instead of redesigning it.

Phase mapping for clarity:

- Phase A = tracker Phase 4
- Phase B = tracker Phase 5
- Phase C = tracker Phase 6
- Phase D = tracker Phase 7
- Phase E = tracker Phases 8-9

### Phase A - Evidence Collection (Implemented)

Implemented collectors under `app/services/evidence/`:

- GitHub collector for file existence and ownership evidence
- HTTP probe collector for URL checks
- incident.io collector for service catalog evidence
- Kubernetes collector for deployment evidence

Phase A exit condition (met):

- at least one collector returns structured evidence with tests
- collectors degrade gracefully when optional credentials are not configured
  (for example, incident.io returns a structured "API token not configured" error
  instead of raising an exception)
- external API behavior should be covered with mocked responses in unit tests

### Phase B - Drift Rules And Alerts (Implemented)

Add rule evaluation under `app/services/drift/` and real endpoints under `app/api/v1/alerts.py`.

Minimum slice:

- base rule interface
- one or two working rules such as `dashboard_dead` and `command_deprecated`
- alert persistence
- alert listing and detail endpoints
- alert resolution endpoint

Exit condition: met.

### Phase C - Scoring (Implemented)

Implement `app/services/scoring/` and `app/api/v1/scores.py`.

Minimum slice:

- score calculation from alerts and extraction quality
- `runbook_scores` persistence
- list and detail score endpoints

Exit condition: met.

### 0 Rs Constraint For Remaining Phases

Phases D and E must stay within 0 Rs recurring spend.

Implementation constraints:

- background jobs must run using local/self-hosted workers with existing Redis
- schedules must run from local/self-hosted runtime (no paid managed schedulers)
- Slack delivery should use incoming webhooks only
- email delivery should use a local/test sink mode first
- observability should start with structured logs and health checks
- paid SaaS tooling must not be required for phase completion

### Phase D - Jobs And Audit Reporting (0 Rs)

Use `AuditJob` for real tracked execution.

Minimum slice:

- move sync/audit work into background execution (implemented for manual audit run and source sync)
- create `AuditJob` rows (implemented)
- implement `/v1/audit/run` (implemented)
- implement audit status polling (implemented through list/detail job endpoints)
- implement a basic JSON audit report (implemented)

Exit condition:

- a manual audit can be triggered, tracked, queried, and summarized through global/service JSON reports

### Phase E - Notifications And Hardening

After the rule pipeline is reliable:

- Slack/email notifier (implemented)
- request logging (implemented)
- rate limiting (implemented)
- CI workflow (implemented)
- contributor documentation (implemented)
- free-only observability path (implemented)
- nightly-scan load-test helper (implemented)

## Current Risks To Respect While Implementing

- Windows-side test runs need `DATABASE_URL`/`ALEMBIC_DATABASE_URL` pointed at `localhost:5433`; in-container app/worker runs use the Docker service hostname `postgres`.
- source sync currently depends on `settings.github_token`, so documentation should describe GitHub auth as app-level configuration for now.
- the sync endpoint now returns `202` with a non-null `audit_job_id`; clients should poll `/v1/audit/jobs/{audit_job_id}` for lifecycle state.
- response formats are mixed today, so any API standardization should be handled deliberately instead of being changed silently.

## Definition Of Done For The Next Iteration

The next code iteration should move beyond the original Phase 0-9 plan.

- notification flow is wired with free-only delivery paths
- hardening tasks are implemented without introducing paid dependencies
- future work should focus on production deployment policy, deeper scale testing,
  frontend/user experience, or CI reliability gates
