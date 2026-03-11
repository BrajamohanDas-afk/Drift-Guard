# Runbook Drift Radar — Design Guidelines

> This is a **backend-first, API-driven product**. Design decisions prioritize reliability, extensibility, and developer experience over visual aesthetics. These guidelines govern code architecture, API design, data modeling, and system behavior.

---

## Principles

### 1. Backend-First, Always
This product has no required UI. Every feature must be fully usable via the REST API. UI is a future concern. Design for API consumers first.

### 2. Evidence Over Opinion
Every drift alert must include **evidence** — concrete data from the live system that justifies the alert. No vague warnings. No false positives without receipts.

### 3. Idempotency
All ingestion and scan operations must be idempotent. Running the same sync twice should produce the same state, not duplicate records. Use content hashes to detect changes.

### 4. Auditability
Every scan, every alert, every score must be traceable. `audit_jobs` and `document_versions` exist to give full historical context. Never delete, only resolve or supersede.

### 5. Fail Gracefully
If one integration fails (e.g., GitHub API is down), the rest of the scan must continue. Partial results are better than no results. Log and surface errors without halting the pipeline.

### 6. Extensibility by Design
Drift rules, ingestion sources, and evidence collectors are all pluggable. New rules should require no changes to the core engine — only a new rule class conforming to the interface.

---

## API Design Standards

### Versioning
All endpoints live under `/v1/`. When breaking changes occur, introduce `/v2/` without removing `/v1/` immediately.

### Response Format
All responses follow a consistent envelope:

```json
{
  "data": { ... },
  "meta": {
    "total": 42,
    "page": 1,
    "per_page": 20
  }
}
```

For errors:
```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "No document found with id: abc-123"
  }
}
```

Async endpoints may additionally return identifiers inside `data`, for example:
```json
{
  "data": {
    "audit_job_id": "job-001"
  }
}
```

### HTTP Status Codes
| Situation | Code |
|---|---|
| Success, data returned | 200 |
| Resource created | 201 |
| Async job triggered | 202 |
| Bad input | 400 |
| Unauthorized | 401 |
| Resource not found | 404 |
| Server error | 500 |

### Naming Conventions
- Use `snake_case` for all JSON keys
- Use `kebab-case` for URL segments
- Boolean fields use `is_` or `has_` prefix: `is_resolved`, `has_score`
- Timestamps always use `_at` suffix: `created_at`, `scored_at`

### Pagination
All list endpoints support:
```
GET /v1/alerts?page=1&per_page=20&severity=critical&service=payments-api
```

---

## Data Modeling Standards

### UUIDs Over Integer IDs
All primary keys are UUID v4. This ensures safe merges, no enumeration attacks, and compatibility with distributed systems in future.

### JSONB for Flexible Evidence
Store variable-shape data (evidence, rule config, source config) in JSONB columns. Index JSONB fields that are queried frequently.

### Immutable Versions
Document content is never updated in place. Each change creates a new `document_version` row. The `documents` table stores metadata only and points to the latest version. This enables drift detection over time.
Entities are extracted from a specific `document_version`, not just from the parent `document`. Persist `document_version_id` on each entity row so historical scans, rescans, and preview-document audits can be tied back to the exact content snapshot that produced them.

### Soft Deletes for Alerts and Documents
Alerts are never hard-deleted. They are `resolved` with a timestamp. This preserves audit history and allows trend analysis.
Documents may be archived via soft delete, but their versions, scores, and historical alerts remain queryable for audit purposes.

---

## Entity Extraction Standards

### Extraction Must Be Deterministic
Given the same document text, extraction must produce the same entity set every time. No randomness, no LLM hallucinations in the extraction layer.

### Entity Types Recognized (MVP)
| Type | Example |
|---|---|
| `service` | `payments-api`, `auth-service` |
| `owner` | `@alice`, `team-platform` |
| `url` | `https://grafana.internal/d/abc` |
| `dashboard` | `grafana:payments-overview`, `datadog:checkout-latency` |
| `command` | `kubectl rollout restart deploy/payments` |
| `env_var` | `STRIPE_API_KEY`, `DB_HOST` |
| `iam_role` | `arn:aws:iam::123456:role/deploy-role` |
| `helm_chart` | `bitnami/postgresql@12.1.0` |
| `cluster` | `prod-us-east-1` |

### Extraction Pipeline Order
1. Pre-process (strip HTML/MDX syntax, normalize whitespace)
2. Run regex patterns per entity type
3. Run NLP pass for implicit service mentions
4. Deduplicate within document
5. Persist to `entities` table

---

## Drift Rules Standards

### Rule Interface
Every rule must implement:
```python
class BaseDriftRule:
    rule_type: str
    severity: str  # 'critical' | 'warning' | 'info'

    def evaluate(self, entity: Entity, evidence: EvidenceStore) -> Optional[Alert]:
        ...
```

### Rule Severity Guidelines
| Severity | Meaning |
|---|---|
| `critical` | Doc references something that no longer exists or is dangerously wrong |
| `warning` | Doc references something outdated or potentially incorrect |
| `info` | Doc is missing optional but useful information |

### Alert Deduplication
Before creating a new alert, check if an identical unresolved alert exists for the same document + rule type + entity value. Do not create duplicates; keep the existing unresolved alert as the system of record.

---

## Scoring Algorithm

Reliability score is calculated per document on a 0–100 scale:

```
base_score = 100
deductions:
  - critical alert: -20 pts each (max -60)
  - warning alert: -8 pts each (max -24)
  - info alert: -2 pts each (max -6)
  - no entities extracted: -30 pts
  - document not updated in 180+ days: -10 pts

floor: 0
```

This weighting is intentionally biased toward confirmed drift over missing structure. In MVP, a stale document with no extracted entities lands at 60 before any alerts, while multiple critical alerts can push the score much lower. Revisit these deductions later if blank documents should fall into `Unreliable` or `Critical` by default.

Score bands:
| Score | Label | Color (future UI) |
|---|---|---|
| 80–100 | Healthy | Green |
| 60–79 | Degraded | Yellow |
| 40–59 | Unreliable | Orange |
| 0–39 | Critical | Red |

---

## Worker & Job Design

### Nightly Scan
- Runs at 02:00 UTC via cron (configurable)
- Creates one `audit_job` per run
- Processes documents in batches of 50
- Max runtime: 2 hours (timeout + alert)
- `audit_job.status` values: `pending`, `running`, `complete`, `partial`, `failed`

### Manual Triggers
- Any audit can be triggered via `POST /v1/audit/run`
- The request may optionally target a single uploaded or changed document via `document_id`
- Returns a `202 Accepted` with the `audit_job.id`
- Client polls `GET /v1/audit/jobs/{id}` for status

### Error Handling in Workers
- Each document scan wrapped in try/except
- Failures logged to `audit_job.error` as structured JSON
- Failed documents do not block the rest of the batch

---

## Integration Standards

### All Connectors Are Read-Only
No integration should ever write, update, or delete anything in a connected system. Drift Radar observes; it does not act.

### Credential Storage
Source credentials stored encrypted in `sources.config` JSONB. Never logged. Never returned in API responses in cleartext. In GET responses, sensitive fields such as `token`, `api_key`, `password`, `secret`, and `webhook_url` must be replaced with the literal string `"***"` so clients can tell a value is present without seeing the secret itself.

### Rate Limiting
All external API calls respect rate limits:
- GitHub: 5000 req/hr (authenticated) — use conditional requests with ETags
- PagerDuty: 960 req/min — batch where possible
- Kubernetes: in-cluster service account preferred

---

## Testing Standards

| Layer | Tool | Coverage Target |
|---|---|---|
| Unit (services, rules) | pytest | 80%+ |
| Integration (API endpoints) | pytest + httpx | All endpoints |
| DB (schema + queries) | pytest + test DB | Core queries |

- Drift rule tests must include both positive (drift detected) and negative (no drift) cases
- Use factories (factory-boy) for test data, not fixtures
- Tests must not make real HTTP calls — mock all external APIs
