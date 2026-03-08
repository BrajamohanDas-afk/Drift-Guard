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
Document content is never updated in place. Each change creates a new `document_version` row. The `documents` table points to the latest. This enables drift detection over time.

### Soft Deletes for Alerts
Alerts are never hard-deleted. They are `resolved` with a timestamp. This preserves audit history and allows trend analysis.

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
Before creating a new alert, check if an identical unresolved alert exists for the same document + rule type + entity value. Do not create duplicates.

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

### Manual Triggers
- Any audit can be triggered via `POST /v1/audit/run`
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
Source credentials stored encrypted in `sources.config` JSONB. Never logged. Never returned in API responses (mask in GET responses).

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
