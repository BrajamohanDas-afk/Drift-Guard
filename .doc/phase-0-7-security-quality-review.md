# Drift Guard Phase 0-7 Security And Quality Review

> UPDATED 2026-05-07: Added task completion checkboxes. H-001 through H-006, M-001 through M-015, and L-001 are complete.
>
> UPDATED 2026-05-09: Phase 8 notification delivery is implemented with the free-only Slack/local email/completion webhook slice.
>
> UPDATED 2026-05-13: Phase 9 hardening/docs baseline now includes request logging, existing rate limits/queue guards, CI, contributing docs, free/local observability guidance, and nightly-scan load-test tooling.

## Scope

Reviewed:

- `.doc/3-tasks.md` phase status through Phase 9
- application code under `app/`
- tests under `tests/`
- Alembic migrations/config
- Docker Compose and `.env.example`
- README/API docs consistency

Review method:

- Used `code-review-excellence`, `multi-reviewer-patterns`, `api-design-principles`, `python-background-jobs`, and `python-configuration` guidance.
- Spawned parallel reviewers for foundation/ingestion, extraction-to-scoring, Phase 7 workers/audit, and cross-cutting security/performance.
- The Phase 7 worker reviewer timed out and was shut down; Phase 7 was reviewed locally instead.

## Verification Snapshot

- `uv run pytest tests/unit -q`: passed, `237 passed`
- `uv run ruff check app tests`: passed
- `uv run pytest tests/unit/test_main_docs.py tests/integration/test_health.py -q`: passed, `4 passed`
- `uv run pytest tests/integration/test_audit.py -q`: passed, `6 passed` against `driftguard_test`
- `uv run pytest tests/integration/test_sources.py -q`: passed, `10 passed` against `driftguard_test`
- `uv run pytest tests/integration -q`: timed out in this audit run because local Postgres/Redis were not reachable from the host
- `docker compose ps -a` showed `postgres` and `redis` exited while `app` and `worker` were still up

Important context:

- A prior run on 2026-05-02 passed the full integration suite when Docker Postgres/Redis were healthy and host-side DB URLs used `localhost:5433`.
- Current audit should treat unit coverage, lint, and source worker integration coverage as verified. Broader integration coverage remains environment-dependent and now requires `DATABASE_URL` to point to a safe test database name.

## Overall Verdict

Phases 0-7 have real implementation behind most checkboxes. The repo is no longer a placeholder.

However, "done" currently means the core audit pipeline, notification slice, security-quality checklist, and local hardening/docs baseline exist, not that the whole product is production-ready. Remaining product work is mostly production deployment policy, deeper scale testing, and future workflows.

Security is partially maintained:

- Good: `/v1/*` routers use API-key auth, API-key comparison uses `hmac.compare_digest`, SQL access is mostly SQLAlchemy expression based, and source responses do not echo source config.
- Not enough for production: deeper scale testing and notification delivery channel policy may still be needed before real external rollout.

## Phase Status

| Phase | Status | Notes |
|---|---|---|
| Phase 0 | Implemented with config fixes | Docker/local env examples are split and known placeholder secrets are rejected at startup. |
| Phase 1 | Implemented with constraints added | AuditJob status constraints and Alembic model metadata imports are now covered. |
| Phase 2 | Implemented with validation tightened | Source config/upload validation and document `path` response gaps are now covered. |
| Phase 3 | Mostly justified | Listed extractors exist and persist version-scoped entities. Cross-phase dependency rule expects entity types not currently extracted. |
| Phase 4 | Implemented with collector hardening | HTTP probe and Kubernetes collectors now validate unsafe targets/segments and disable redirects before automation wiring. |
| Phase 5 | Implemented service layer, incomplete scan lifecycle | Rules, alert APIs, and dedupe exist, but no recurring scan reconciliation of stale alerts. |
| Phase 6 | Implemented with deleted-doc filtering | Scoring works and score APIs now exclude deleted documents. |
| Phase 7 | Implemented with full audit scan lifecycle | Audit runs sync sources, collect supported evidence, evaluate rules, reconcile alerts, refresh scores, and update job counters. |
| Phase 8 | Implemented | Free-only Slack webhook, local email sink, routing, audit completion webhook support, delivery logs, and tests are implemented. |
| Phase 9 | Implemented baseline | API key auth, docs route gating, request logging, rate limits, queue guards, README updates, CI, contributing docs, observability guidance, and nightly-scan load-test tooling exist. |

## Task Completion Tracker

Use this as the working checklist. Checked items are fixed and locally verified; unchecked items are still open or intentionally deferred.

High priority:

- [x] H-001 Audit jobs run full drift detection
- [x] H-002 Docker and placeholder secret exposure
- [x] H-003 `.env.example` matches Docker and host workflows
- [x] H-004 HTTP probe collector SSRF hardening
- [x] H-005 Kubernetes collector path hardening
- [x] H-006 Integration tests cannot truncate the wrong database

Medium priority:

- [x] M-001 Alembic autogenerate imports model metadata reliably
- [x] M-002 AuditJob status is constrained in DB/API schemas
- [x] M-003 Source creation validates config earlier
- [x] M-004 Direct upload input and identity are tightened
- [x] M-005 Document API returns source path
- [x] M-006 Git sync has repo size and timeout budgets
- [x] M-007 Alerts self-reconcile when drift is fixed
- [x] M-008 Score APIs exclude deleted documents
- [x] M-009 Dependency rule matches extractor output
- [x] M-010 Alert evidence redacts sensitive URL data
- [x] M-011 Hot query indexes are added
- [x] M-012 Rate limiting and queue abuse guards exist
- [x] M-013 End-to-end worker integration coverage exists
- [x] M-014 `ruff check app tests` is clean
- [x] M-015 README matches current APIs and worker behavior

Low priority:

- [x] L-001 Public docs/OpenAPI are gated for production

## High Priority Findings

### H-001 Audit Jobs Did Not Run Full Drift Detection

Location:

- `app/workers/audit_run_task.py:51`
- `app/workers/audit_run_task.py:60`

Problem:

`audit_run_task` syncs sources and increments `alerts_created_delta=0`. It does not collect evidence, invoke `RulesEngine`, call `AlertService.persist_alerts`, reconcile old alerts, or refresh scores as part of the audit run.

Impact:

Routine audit jobs can complete successfully without detecting new drift. Phase 5/6 services are implemented, but the recurring product workflow is not fully wired.

Solution:

Add a scan orchestrator service that:

- loads active documents and latest entities
- collects configured evidence with safe budgets
- evaluates rules through `RulesEngine`
- persists new alerts through `AlertService`
- resolves stale alerts that no longer fire for the same scan scope
- refreshes scores
- updates `AuditJob.docs_scanned` and `AuditJob.alerts_created`

Status:

Fixed by adding an audit scan service and wiring `audit_run_task` through source sync, supported evidence collection, rule evaluation, alert persistence/reconciliation, score refresh, and audit job progress updates.

Important:

This was fixed before Phase 8 notification delivery work, so notification delivery can now build on real alert counts.

### H-002 Docker And Placeholder Secret Exposure Was Present

Location:

- `docker-compose.yml:5`
- `docker-compose.yml:29`
- `docker-compose.yml:45`
- `.env.example:4`
- `.env.example:7`

Problem:

App, Postgres, and Redis are published to host interfaces. Postgres uses `drift/drift`, Redis has no auth, and placeholder API/secret values are accepted as valid config.

Impact:

On a reachable machine, the DB and queue can be exposed directly. If someone copies `API_KEY=change-me`, API auth is weak in practice.

Solution:

- Bind dev ports to `127.0.0.1` where host access is needed.
- Do not publish Postgres/Redis host ports by default, or document them as local-only.
- Add Redis auth for shared environments.
- Reject known placeholder secret values at startup.
- Use separate `.env.docker.example` and `.env.local.example`.

Status:

Fixed by binding Compose ports to `127.0.0.1`, adding Redis password configuration, rejecting known placeholder API/secret/token values in settings, and splitting Docker/host env examples.

### H-003 `.env.example` Did Not Match Docker And Host Workflows

Location:

- `.env.example:2`
- `.doc/2-implementation_plan.md:199`
- `docker-compose.yml:29`

Problem:

`ALEMBIC_DATABASE_URL` points to `localhost:5432`, while Docker-internal Alembic needs `postgres:5432` and Windows host-side tests need `localhost:5433`.

Impact:

Fresh setup can fail migrations/tests even though Phase 0 says env config is done.

Solution:

Split examples:

- Docker/app container: `postgres:5432`, `redis:6379`
- Host-side tests on Windows: `localhost:5433`, `localhost:6379`

Also update README commands to show the correct environment variables for each workflow.

Status:

Fixed by replacing `.env.example` with guidance and adding `.env.docker.example` plus `.env.local.example` with Docker-internal, host-side, and safe test database URLs.

### H-004 HTTP Probe Collector Was SSRF-Prone Before Wiring

Location:

- `app/services/evidence/http_collector.py:28`
- `app/services/evidence/http_collector.py:30`

Problem:

`HttpProbeCollector` fetches arbitrary URLs and follows redirects without scheme, host, or IP-range validation.

Impact:

Once wired to ingested document URLs, a user with upload/source access could probe loopback, link-local, private networks, or cloud metadata endpoints.

Solution:

- Allow only `http`/`https`.
- Resolve DNS and block loopback, private, link-local, multicast, and reserved CIDRs.
- Disable redirects or revalidate every redirect target.
- Consider per-collector allowlists.

Status:

Fixed by validating `http`/`https` probe targets, rejecting non-public DNS/IP targets, and disabling redirects.

### H-005 Kubernetes Collector Had Path Injection Risk

Location:

- `app/services/evidence/kubernetes_collector.py:94`
- `app/services/evidence/kubernetes_collector.py:105`

Problem:

`namespace` and `deployment` are interpolated raw into an authenticated Kubernetes API URL, and redirects are enabled.

Impact:

User-derived values containing `/`, `..`, or query delimiters could steer a bearer-token request to unintended Kubernetes API paths.

Solution:

- Validate namespace/deployment using Kubernetes DNS-1123 rules.
- Percent-encode path segments.
- Disable redirects for bearer-token Kubernetes requests.

Status:

Fixed by validating Kubernetes path segments, encoding them in the API URL, and disabling redirects for bearer-token requests.

### H-006 Integration Tests Can Truncate The Wrong Database

Location:

- `tests/conftest.py:14`
- `tests/conftest.py:34`
- `tests/conftest.py:36`

Problem:

The integration fixture truncates tables in whatever `DATABASE_URL` points to.

Impact:

If a developer accidentally runs tests against staging or production, test setup can delete real data.

Solution:

Add a hard guard before truncation:

- require database name to contain `test`
- or require an explicit `ALLOW_TEST_DB_TRUNCATE=true`
- or create/drop a disposable schema per test run

## Medium Priority Findings

### M-001 Alembic Autogenerate Metadata Is Fragile

Location:

- `alembic/env.py:21`
- `alembic/env.py:22`
- `app/models/__init__.py:1`

Problem:

Alembic uses `Base.metadata` but does not import model modules in `env.py`. Future autogenerate/check workflows can miss models if they have not been imported elsewhere.

Solution:

Import `app.models` in `alembic/env.py` before assigning `target_metadata`.

### M-002 AuditJob Status Is Free-Form In Model/API Response

Location:

- `app/models/audit_job.py:13`
- `app/schemas/audit_job.py:23`
- `tests/unit/test_models.py:64`

Problem:

The DB column accepts any text, `AuditJobResponse.status` is `Optional[str]`, and tests accept `status="complete"` even though the lifecycle uses `pending/running/completed/failed`.

Solution:

- Use `AuditJobStatus` in response schemas.
- Add DB check constraint or enum.
- Update tests to reject invalid statuses.

### M-003 Source Creation Defers Too Much Validation

Location:

- `app/schemas/source.py:10`
- `app/api/v1/sources.py:34`
- `app/services/ingestion/source_sync_service.py:45`

Problem:

Source config accepts weak `repo_url`, `branch`, and `path_filter` values, and repo URL validation is mostly deferred until sync.

Solution:

- Validate GitHub URL shape at `POST /v1/sources`.
- Forbid unknown config fields with Pydantic config.
- Normalize branch/path strings.
- Keep network-dependent repo existence checks in sync worker.

### M-004 Direct Upload Input And Identity Are Too Loose

Location:

- `app/api/v1/documents.py:20`
- `app/api/v1/documents.py:40`
- `app/services/ingestion/document_ingestion_service.py:64`

Problem:

Upload accepts any UTF-8 file and direct-upload dedupe uses filename as identity.

Impact:

Non-Markdown content can enter the pipeline. Two unrelated uploads named `runbook.md` merge histories.

Solution:

- Enforce `.md`/`.markdown` extension or accepted content type.
- Add a clearer direct-upload identity strategy.
- If filename replacement is intended, document it explicitly.

### M-005 Document API Omits Source Path

Location:

- `app/schemas/document.py:16`
- `app/services/ingestion/source_sync_service.py:101`

Problem:

Source-backed documents are keyed by `source_id + path`, but `path` is not returned by list/detail document responses.

Impact:

Clients cannot distinguish same-named synced files from different folders.

Solution:

Add `path` to `DocumentResponse` and integration tests.

### M-006 Git Sync Has No Repo Size Budget

Location:

- `app/services/ingestion/git_ingestor.py:43`
- `app/services/ingestion/source_sync_service.py:82`

Problem:

Sync recursively collects Markdown files without file count, byte size, depth, or timeout budgets.

Impact:

Large repos can exhaust worker memory, DB storage, and GitHub rate limits.

Solution:

Add max files, max bytes per file, max total bytes, timeout budgets, and partial sync reporting.

### M-007 Alerts Do Not Self-Reconcile When Drift Is Fixed

Location:

- `app/services/drift/alert_service.py:95`
- `app/services/drift/alert_service.py:138`

Problem:

Alert persistence dedupes and creates alerts, but there is no scan-scoped reconciliation that resolves alerts that stop firing.

Impact:

Fixed runbooks or recovered evidence can leave stale unresolved alerts that keep depressing scores.

Solution:

Add a rule-run persistence API that resolves missing fingerprints for the document/rule scope and refreshes affected scores.

### M-008 Score APIs Include Deleted Documents

Location:

- `app/services/scoring/scoring_service.py:196`
- `app/services/scoring/scoring_service.py:226`
- `app/api/v1/scores.py:43`

Problem:

Score list/detail queries do not join `Document` or filter `Document.is_deleted`.

Impact:

Soft-deleted runbooks can still appear in `/v1/scores` and `/v1/scores/{document_id}`.

Solution:

Filter score queries to active documents and return `404` for deleted documents.

### M-009 Dependency Rule Expects Entities The Extractor Does Not Produce

Location:

- `app/services/drift/rules/dependency_undocumented_rule.py:11`

Problem:

The rule expects `dependency`, `service_dependency`, or `depends_on` entities, but the extraction pipeline does not produce those entity types.

Impact:

The rule can pass synthetic tests but cannot see documented dependencies from real ingested docs.

Solution:

Add and wire a dependency extractor, or change the rule to use entity types the pipeline already extracts.

### M-010 Alert Evidence Can Leak Sensitive URL Data

Location:

- `app/services/drift/rules/dashboard_dead_rule.py:143`
- `app/schemas/alert.py:12`

Problem:

Raw dashboard targets are persisted in alert evidence and returned through alert APIs.

Impact:

Signed URLs, userinfo, or token query parameters in docs can leak into DB/API responses.

Solution:

Reject URLs with embedded credentials and redact sensitive query parameters before persisting alert evidence.

### M-011 Missing Indexes On Hot Queries

Location:

- `alembic/versions/04c74d378803_create_all_tables.py:68`
- `app/services/drift/alert_service.py:164`
- `app/services/scoring/scoring_service.py:259`

Problem:

Hot alert, score, entity, and audit-job filters/orderings lack supporting indexes.

Solution:

Add indexes such as:

- alerts: `(resolved, document_id, severity, rule_type, created_at)`
- scores: `(document_id, scored_at)`
- entities: `(document_version_id, entity_type, value)`
- audit jobs: `(status, started_at)`

### M-012 No Rate Limiting Or Queue Abuse Guard

Location:

- `app/api/v1/documents.py:18`
- `app/api/v1/sources.py:72`
- `app/api/v1/audit.py:34`

Problem:

Heavy endpoints are API-key protected but not rate limited or quota bounded.

Impact:

A leaked/shared API key can create uploads, sync jobs, audit jobs, GitHub calls, DB writes, and Redis queue growth.

Solution:

Add per-key/IP rate limits, job quotas, queue depth checks, and structured logs for rejected work.

### M-013 End-To-End Worker Integration Coverage Was Missing

Location:

- `tests/integration/test_sources.py:83`
- `tests/integration/test_sources.py:117`
- `tests/conftest.py:34`

Problem:

Tests cover mocked enqueue behavior and direct sync service behavior, but not endpoint -> Redis/ARQ -> worker -> DB ingestion in one run.

Solution:

Add an integration test using real test Redis/worker, or invoke worker task functions against the test DB after asserting enqueue contracts.

### M-014 Ruff Was Not Clean Across `app tests`

Location:

- `app/models/*.py`
- `app/main.py`
- `tests/unit/test_models.py`
- `tests/unit/test_extractors.py`

Problem:

`uv run ruff check app tests` previously reported import-order, unused-import, and line-length issues.

Solution:

Run targeted `ruff --fix` for auto-fixable import issues, then manually wrap long lines. Add full ruff to CI once clean.

### M-015 README Is Stale

Location:

- `README.md:149`
- `README.md:155`
- `README.md:156`

Problem:

README still says `/v1/scores` and `/v1/audit` are placeholders, while both are now implemented.

Solution:

Update README API surface, auth header usage, source sync behavior, worker/Redis notes, and host-vs-Docker DB URL guidance.

## Low Priority Findings

### L-001 Public Docs/OpenAPI Needed Production Gating

Location:

- `app/main.py:4`
- `app/main.py:16`

Problem:

FastAPI docs/OpenAPI are public by default.

Impact:

Endpoint discovery is exposed, though API-key auth still protects `/v1/*`.

Solution:

Keep `/docs` enabled for local/dev. Add config to disable or protect docs in production.

Status:

Fixed by adding `PUBLIC_API_DOCS_ENABLED`; `/docs`, `/redoc`, and `/openapi.json` stay enabled by default for local development and are disabled when the flag is false.

## Security Summary

No reviewer found an obvious SQL injection path or auth bypass in the implemented `/v1` API surface. API-key enforcement is consistently applied to documents, sources, alerts, scores, and audit routers.

Security-quality review is complete. Remaining production work is outside this review checklist:

- production deployment policy, deeper scale testing, and future product workflows remain open.

Recommended security order:

- [x] Fix Docker exposure and placeholder-secret validation.
- [x] Add test DB truncation guard.
- [x] Harden HTTP and Kubernetes collectors.
- [x] Add rate limiting/job quota controls.
- [x] Add production docs toggle.

## Recommended Fix Order

- [x] Fix `.env.example` / Docker local-vs-container configuration and reject placeholder secrets.
- [x] Add test DB guard to `tests/conftest.py`.
- [x] Update README to match current APIs and worker behavior.
- [x] Clean full `ruff check app tests`.
- [x] Harden HTTP/Kubernetes collectors before wiring them into automatic scans.
- [x] Build the scan orchestrator that connects ingestion, evidence, rules, alerts, reconciliation, and scoring.
- [x] Filter deleted documents from score APIs.
- [x] Add AuditJob status constraints and indexes for hot queries.
- [x] Improve source/upload validation and expose document `path`.
- [x] Start Phase 8 notification delivery only after the audit pipeline can produce real alert counts.

## Task Tracker Recommendation

Phase 7 can now be described as complete end-to-end drift detection for the supported collectors/rules in this repo.

- [x] `N-014A Wire audit runs to evidence, rules, alert reconciliation, and scoring`

Phase 8 notification delivery is implemented:

- [x] `N-014 Implement Phase 8 notification delivery`
