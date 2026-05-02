# Drift Guard Swagger Full Test Runbook

Use this checklist to manually test the full API surface in Swagger UI.

## 1. Prerequisites

1. Start services and app:
```powershell
docker compose up -d --build app postgres redis
```
2. Run migrations:
```powershell
docker compose exec app uv run alembic upgrade head
```
3. Confirm app is up:
```powershell
curl http://localhost:8000/health
```
Expected:
```json
{"status":"ok"}
```
4. Open Swagger UI:
`http://localhost:8000/docs`

## 2. Authentication Check (for all `/v1/*` routes)

All v1 endpoints require header `x-api-key`.

1. Call `GET /v1/documents` without key -> expect `401`.
2. Call `GET /v1/documents` with valid `x-api-key` from your `.env` -> expect `200`.

## 3. Documents API

## 3.1 Upload document
Endpoint: `POST /v1/documents/upload`

1. Click `Try it out`.
2. Upload a `.md` file, example content:
```md
# Payments Runbook
owner: sre-team
service: payments-api
dashboard: https://grafana.example.com/d/payments
```
3. Execute.
4. Expect `201` with document object. Save returned `id` as `DOCUMENT_ID`.

## 3.2 List documents
Endpoint: `GET /v1/documents?page=1&per_page=20`

1. Execute with valid key.
2. Expect `200`.
3. Verify `meta.total >= 1` and `data` includes `DOCUMENT_ID`.

## 3.3 Get document by id
Endpoint: `GET /v1/documents/{document_id}`

1. Use `DOCUMENT_ID`.
2. Expect `200`.

## 3.4 Delete document
Endpoint: `DELETE /v1/documents/{document_id}`

1. Use `DOCUMENT_ID`.
2. Expect `200` and `is_deleted: true`.
3. Re-run `GET /v1/documents/{document_id}` -> expect `404`.

## 4. Sources API

## 4.1 Create source
Endpoint: `POST /v1/sources`

Body:
```json
{
  "name": "DriftGuard Repo",
  "type": "git",
  "config": {
    "repo_url": "https://github.com/your-org/your-repo",
    "branch": "main",
    "path_filter": "docs/"
  }
}
```

1. Execute.
2. Expect `201`. Save `id` as `SOURCE_ID`.

## 4.2 List sources
Endpoint: `GET /v1/sources`

1. Execute.
2. Expect `200`.
3. Verify response contains `SOURCE_ID`.

## 4.3 Sync source
Endpoint: `POST /v1/sources/{source_id}/sync`

1. Use `SOURCE_ID`.
2. If `GITHUB_TOKEN` is configured: expect `202` with a non-null `audit_job_id` and `status: pending`.
3. If token is missing: expect `400` with `GITHUB_TOKEN is not configured`.
4. Poll `GET /v1/audit/jobs/{audit_job_id}` to watch the background sync lifecycle.

## 5. Alerts API

## 5.1 List alerts
Endpoint: `GET /v1/alerts`

1. Execute.
2. Expect `200` with paginated payload.
3. Optional filters to test:
   - `resolved=true`
   - `severity=high`
   - `rule_type=...`
   - `document_id=<uuid>`

## 5.2 Get alert by id
Endpoint: `GET /v1/alerts/{alert_id}`

1. Use an existing alert id from list -> expect `200`.
2. Use random UUID -> expect `404`.

## 5.3 Resolve alert
Endpoint: `PATCH /v1/alerts/{alert_id}/resolve`

1. Use unresolved alert id.
2. Expect `200` and `resolved: true`.
3. Re-run `GET /v1/alerts/{alert_id}` to confirm `resolved_at` is populated.

## 6. Scores API (Phase 6)

## 6.1 List scores
Endpoint: `GET /v1/scores?page=1&per_page=20`

1. Execute.
2. Expect `200` with shape:
```json
{
  "data": [],
  "meta": {
    "total": 0,
    "page": 1,
    "per_page": 20
  }
}
```
3. If score snapshots exist, `data` contains latest score per document.

## 6.2 Get score by document id
Endpoint: `GET /v1/scores/{document_id}`

1. Use document id that has score snapshot -> expect `200`.
2. Use document id with no score snapshot -> expect `404` (`Score not found`).

Notes:
- Score snapshots are created when scoring service is triggered by alert persistence/resolve flows.
- If you have no alert/score data yet, scores endpoints still pass with empty list / not found behavior.

## 7. Audit API

## 7.1 Trigger audit run
Endpoint: `POST /v1/audit/run`

Body is optional:
```json
{
  "triggered_by": "manual"
}
```

1. Execute with valid key.
2. Expect `202` with an audit job object.
3. Save `id` as `AUDIT_JOB_ID`.
4. If Redis/worker queue is unavailable, expect `503` and the created job is marked failed.

## 7.2 List audit jobs
Endpoint: `GET /v1/audit/jobs?page=1&per_page=20`

1. Execute with valid key.
2. Expect `200` with `data` and `meta`.
3. Optional filter: `status=pending`, `running`, `completed`, or `failed`.

## 7.3 Get audit job by id
Endpoint: `GET /v1/audit/jobs/{audit_job_id}`

1. Use `AUDIT_JOB_ID`.
2. Expect `200` with lifecycle fields such as `status`, `docs_scanned`, `started_at`, `completed_at`, and `error`.
3. Use random UUID -> expect `404`.

## 7.4 Get global audit report
Endpoint: `GET /v1/audit/report`

1. Execute with valid key.
2. Expect `200` with `scope: global`.
3. Verify the response includes:
   - `latest_audit_job`
   - `totals.documents`
   - `totals.unresolved_alerts`
   - `alerts_by_severity`
   - `score_summary`
   - `lowest_scoring_documents`

## 7.5 Get service audit report
Endpoint: `GET /v1/audit/service/{service_name}`

1. Use a known service name from a document `service_name` field or latest extracted `service` entity.
2. Expect `200` with `scope: service` and `service_name` matching the request.
3. Use a missing service name -> expect `404`.

Notes:
- Source sync runs in the background and returns a tracked `audit_job_id`.

## 8. Non-v1 Endpoint

## 8.1 Health check
Endpoint: `GET /health`

1. Execute.
2. Expect `200` and `{"status":"ok"}`.

## 9. Quick Negative Tests

1. Invalid API key on any `/v1/*` endpoint -> `401`.
2. Invalid UUID in path params -> `422`.
3. `per_page > 100` on paginated endpoints -> `422` (request validation).
4. Upload non-UTF8 file on `/v1/documents/upload` -> `400`.
5. Upload file >1 MB on `/v1/documents/upload` -> `413`.

## 10. Pass/Fail Checklist

- [ ] Auth enforcement works (`401` without key, `200` with key)
- [ ] Documents upload/list/get/delete works
- [ ] Sources create/list/sync works (or returns expected token/config error)
- [ ] Alerts list/get/resolve works
- [ ] Scores list/get works with expected empty/data behavior
- [ ] Audit run/job/report endpoints work
- [ ] Health check works
- [ ] Error codes and validation behavior match expectations
