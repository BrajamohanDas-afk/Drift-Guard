# Drift Guard - Implementation Plan

> UPDATED 2026-03-30: Rewritten to match the current codebase. This is now a status-aware implementation plan, not a greenfield design doc.

## Current Architecture

The repository already has the ingestion foundation in place.

### Present folder shape

```text
Drift-Guard/
|-- app/
|   |-- api/v1/
|   |   |-- audit.py          # placeholder router
|   |   |-- alerts.py         # placeholder router
|   |   |-- documents.py      # implemented
|   |   |-- scores.py         # placeholder router
|   |   `-- sources.py        # implemented
|   |-- config.py
|   |-- database.py
|   |-- dependencies/auth.py
|   |-- models/
|   |-- schemas/
|   |-- services/
|   |   |-- extraction/       # implemented extractors
|   |   |-- ingestion/        # implemented upload + git ingestion helpers
|   |   |-- alerting/         # placeholder package
|   |   |-- drift/            # placeholder package
|   |   |-- evidence/         # placeholder package
|   |   `-- scoring/          # placeholder package
|   `-- workers/              # placeholder files
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

### Reserved but not implemented yet

- `/v1/alerts/*`
- `/v1/scores/*`
- `/v1/audit/*`

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
3. Use `GitIngestor` to recursively fetch Markdown files from GitHub.
4. Upsert each file using `source_id + path` as identity.
5. Reuse version history when content is unchanged.
6. Update `last_synced_at`.

## What The Codebase Is Ready For Next

The next implementation phase should build on top of the current ingestion pipeline instead of redesigning it.

### Phase A - Evidence Collection

Add real collectors under `app/services/evidence/`:

- GitHub collector for file existence and ownership evidence
- HTTP probe collector for URL checks
- PagerDuty collector for service existence evidence
- Kubernetes collector for deployment evidence
- optional first collector abstraction for shared request behavior

Exit condition:

- at least one collector returns structured evidence with tests
- collectors degrade gracefully when optional credentials are not configured
  (for example, PagerDuty returns a structured "API token not configured" error
  instead of raising an exception)
- external API behavior should be covered with mocked responses in unit tests

### Phase B - Drift Rules And Alerts

Add rule evaluation under `app/services/drift/` and real endpoints under `app/api/v1/alerts.py`.

Minimum slice:

- base rule interface
- one or two working rules such as `dashboard_dead` and `command_deprecated`
- alert persistence
- alert listing and detail endpoints
- alert resolution endpoint

Exit condition:

- a synced or uploaded document can generate a real alert visible through the API

### Phase C - Scoring

Implement `app/services/scoring/` and `app/api/v1/scores.py`.

Minimum slice:

- score calculation from alerts and extraction quality
- `runbook_scores` persistence
- list and detail score endpoints

Exit condition:

- each document can return a current reliability score and breakdown

### Phase D - Jobs And Audit Reporting

Use `AuditJob` for real tracked execution.

Minimum slice:

- move sync/audit work into background execution
- create `AuditJob` rows
- implement `/v1/audit/run`
- implement audit status polling
- implement a basic JSON audit report

Exit condition:

- a manual audit can be triggered, tracked, and queried

### Phase E - Notifications And Hardening

After the rule pipeline is reliable:

- Slack/email notifier
- request logging
- rate limiting
- CI workflow
- contributor documentation

## Current Risks To Respect While Implementing

- `alerts`, `scores`, and `audit` routers are currently empty, so public docs should not imply those features already work.
- source sync currently depends on `settings.github_token`, so documentation should describe GitHub auth as app-level configuration for now.
- the sync endpoint returns `202`, but it performs work inline and returns `audit_job_id: null`; background execution is still pending.
- response formats are mixed today, so any API standardization should be handled deliberately instead of being changed silently.

## Definition Of Done For The Next Iteration

The next code iteration should not stop at placeholders. It should deliver the first end-to-end drift detection slice:

- evidence collector
- drift rule
- alert persistence
- alert API
- tests proving the flow works
