# Runbook Drift Radar — Implementation Plan

## Folder Structure

```
runbook-drift-radar/
├── app/
│   ├── main.py                    # FastAPI app entrypoint
│   ├── config.py                  # Settings via pydantic-settings
│   ├── database.py                # DB engine + session factory
│   ├── models/                    # SQLAlchemy models
│   │   ├── source.py
│   │   ├── document.py
│   │   ├── document_version.py
│   │   ├── entity.py
│   │   ├── alert.py
│   │   ├── runbook_score.py
│   │   └── audit_job.py
│   ├── schemas/                   # Pydantic schemas (request/response)
│   │   ├── document.py
│   │   ├── alert.py
│   │   └── score.py
│   ├── api/                       # FastAPI routers
│   │   ├── v1/
│   │   │   ├── documents.py
│   │   │   ├── sources.py
│   │   │   ├── alerts.py
│   │   │   ├── scores.py
│   │   │   └── audit.py
│   ├── services/                  # Business logic
│   │   ├── ingestion/
│   │   │   ├── markdown_ingestor.py
│   │   │   ├── git_ingestor.py
│   │   │   ├── confluence_ingestor.py      # future expansion
│   │   │   └── notion_ingestor.py          # future expansion
│   │   ├── extraction/
│   │   │   ├── entity_extractor.py
│   │   │   ├── url_checker.py
│   │   │   ├── dashboard_matcher.py
│   │   │   └── command_parser.py
│   │   ├── drift/
│   │   │   ├── rules_engine.py
│   │   │   ├── rules/
│   │   │   │   ├── owner_rule.py
│   │   │   │   ├── dashboard_rule.py
│   │   │   │   ├── command_rule.py
│   │   │   │   ├── helm_rule.py
│   │   │   │   └── dependency_rule.py
│   │   ├── evidence/
│   │   │   ├── github_collector.py
│   │   │   ├── kubernetes_collector.py
│   │   │   ├── aws_collector.py            # future expansion
│   │   │   └── pagerduty_collector.py
│   │   ├── scoring/
│   │   │   └── scorer.py
│   │   └── alerting/
│   │       ├── slack_notifier.py
│   │       └── email_notifier.py
│   ├── workers/                   # Celery/Arq tasks
│   │   ├── nightly_scan.py
│   │   ├── ingest_task.py
│   │   └── score_task.py
│   └── utils/
│       ├── http.py
│       └── text.py
├── alembic/                       # DB migrations
│   └── versions/
├── tests/
│   ├── unit/
│   └── integration/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## Database Schema

### `sources`
```sql
CREATE TABLE sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  type TEXT NOT NULL,           -- 'git', 'confluence', 'notion', 'upload'
  config JSONB NOT NULL,        -- connection config (url, token, etc.)
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### `documents`
```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES sources(id),
  title TEXT NOT NULL,
  doc_type TEXT,                -- 'runbook', 'sop', 'onboarding', 'recovery'
  service_name TEXT,
  is_deleted BOOLEAN NOT NULL DEFAULT false,
  deleted_at TIMESTAMPTZ,
  latest_version_id UUID,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### `document_versions`
```sql
CREATE TABLE document_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id),
  raw_content TEXT NOT NULL,
  normalized_content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  version_number INT NOT NULL,
  captured_at TIMESTAMPTZ DEFAULT now()
);
```

### `entities`
```sql
CREATE TABLE entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id),
  document_version_id UUID NOT NULL REFERENCES document_versions(id),
  entity_type TEXT NOT NULL,    -- 'service', 'owner', 'url', 'dashboard', 'command', 'env_var', 'iam_role', 'helm_chart', 'cluster'
  value TEXT NOT NULL,
  context TEXT,                 -- surrounding text snippet
  extracted_at TIMESTAMPTZ DEFAULT now()
);
```

`document_id` supports document-level queries, while `document_version_id` is the authoritative link to the exact content snapshot that produced the entity. This matters for rescans and CI/CD preview documents.

### `runbook_scores`
```sql
CREATE TABLE runbook_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id),
  score NUMERIC(5,2) NOT NULL,  -- 0.00 to 100.00
  breakdown JSONB,              -- per-rule score details
  scored_at TIMESTAMPTZ DEFAULT now()
);
```

### `alerts`
```sql
CREATE TABLE alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id),
  rule_type TEXT NOT NULL,
  severity TEXT NOT NULL,       -- 'critical', 'warning', 'info'
  message TEXT NOT NULL,
  evidence JSONB,               -- what we found in the live system
  resolved BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
```

### `audit_jobs`
```sql
CREATE TABLE audit_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  triggered_by TEXT,            -- 'schedule', 'manual', 'webhook'
  status TEXT DEFAULT 'pending',
  docs_scanned INT,
  alerts_created INT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error TEXT
);
```

---

## API Endpoints

### Documents
| Method | Path | Description |
|---|---|---|
| POST | `/v1/documents/upload` | Upload a runbook (Markdown file) |
| GET | `/v1/documents` | List all documents |
| GET | `/v1/documents/{id}` | Get a single document |
| DELETE | `/v1/documents/{id}` | Remove a document |

### Sources
| Method | Path | Description |
|---|---|---|
| POST | `/v1/sources` | Connect a new source (Git in MVP; additional source types in expansion phases) |
| GET | `/v1/sources` | List connected sources |
| POST | `/v1/sources/{id}/sync` | Trigger manual sync of a source |

### Alerts
| Method | Path | Description |
|---|---|---|
| GET | `/v1/alerts` | List all alerts (filterable by service, severity) |
| GET | `/v1/alerts/{id}` | Get a single alert with evidence |
| PATCH | `/v1/alerts/{id}/resolve` | Mark alert as resolved |

### Scores
| Method | Path | Description |
|---|---|---|
| GET | `/v1/scores` | List reliability scores for all docs |
| GET | `/v1/scores/{document_id}` | Get score breakdown for a doc |

### Audit
| Method | Path | Description |
|---|---|---|
| POST | `/v1/audit/run` | Trigger a manual audit for all docs or a specific `document_id` |
| GET | `/v1/audit/jobs` | List audit job history |
| GET | `/v1/audit/jobs/{id}` | Get one audit job for polling |
| GET | `/v1/audit/report` | Get latest audit report as JSON in MVP (`format=json` only; PDF is post-MVP) |
| GET | `/v1/audit/service/{service_name}` | Get findings for a specific service |

---

## Drift Rules (Phase 2)

| Rule | Trigger | Data Source |
|---|---|---|
| `owner_missing` | Doc names an owner not found in GitHub/PagerDuty | GitHub CODEOWNERS, PagerDuty |
| `dashboard_dead` | Doc URL returns non-200 | HTTP probe |
| `command_deprecated` | Doc references a script path that no longer exists in repo | GitHub file tree |
| `helm_version_stale` | Doc mentions a Helm chart version not in current deployment | Kubernetes / Helm |
| `dependency_undocumented` | Service exists in prod but has no runbook | Kubernetes + documents table |

---

## Nightly Scan Job Flow

```
1. Create audit_job record (status=running)
2. For each connected source → pull latest docs
3. For each doc → run entity extraction
4. For each entity set → run all drift rules
5. Create alerts for any violations found
6. Run scoring on every document
7. Send Slack/email digest if alerts exist
8. Update audit_job (status=complete, counts)
```

## MVP Boundaries

- `GET /v1/audit/report` is JSON-only in MVP. If `format=pdf` is requested, return a clear unsupported-format error.
- Weekly digest scheduling is post-MVP unless promoted into a first-class config model and API. MVP only supports end-of-audit notifications configured at the application level.

---

## Development Milestones

### Week 1
- [ ] Postgres schema + Alembic migrations
- [ ] FastAPI app scaffolding
- [ ] Docker Compose (app + db + redis)
- [ ] `POST /v1/documents/upload` (Markdown ingest)

### Week 2
- [ ] Entity extraction pipeline (URLs, service names, owners, commands)
- [ ] `GET /v1/alerts` and alert model
- [ ] HTTP URL probe (dashboard_dead rule)

### Week 3
- [ ] GitHub source connector
- [ ] `owner_missing` and `command_deprecated` drift rules
- [ ] Celery/Arq worker setup

### Week 4
- [ ] Scoring algorithm + `runbook_scores` table
- [ ] Nightly scan job
- [ ] `GET /v1/scores` endpoints

### Week 5
- [ ] Slack webhook notifier
- [ ] Audit job tracking + `/v1/audit/*` endpoints
- [ ] Manual audit trigger

### Week 6
- [ ] `helm_version_stale` + `dependency_undocumented` rules
- [ ] Kubernetes connector (basic)
- [ ] Integration tests
- [ ] README + API docs (Swagger auto-generated)
