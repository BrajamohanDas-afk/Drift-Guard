# Runbook Drift Radar — Master Plan

## Vision

**Runbook Drift Radar** is a backend-first documentation validity engine that continuously monitors whether runbooks, SOPs, onboarding guides, and recovery docs reflect reality. It detects "doc rot" before it causes incidents — not after.

---

## Problem Statement

Engineering teams write runbooks during incidents or onboarding and then forget them. Over time:
- Services get renamed, owners change
- Dashboard URLs go dead
- Commands reference deprecated scripts
- Helm charts and dependencies drift
- New services appear in production with zero documentation

No one notices until a 3am incident when the runbook is wrong. **Runbook Drift Radar solves this silently, continuously, and automatically.**

---

## Core Value Proposition

| Without Drift Radar | With Drift Radar |
|---|---|
| Docs rot silently | Drift is detected on a schedule |
| Teams discover bad docs during incidents | Teams get alerted before incidents |
| No confidence metric for docs | Every runbook gets a "reliability score" |
| Manual doc audits (never done) | Automated nightly audit jobs |

---

## Product Goals

1. **Ingest** runbooks from any source (Markdown, Confluence, Notion, Git)
2. **Connect** to live infra metadata (GitHub, Kubernetes, AWS, PagerDuty, Jira, CI/CD)
3. **Extract** structured entities from docs (services, owners, URLs, commands, env vars, IAM roles)
4. **Detect** drift between doc entities and live system state
5. **Score** each runbook with a reliability confidence rating
6. **Alert** teams via Slack, email, or webhook
7. **Expose** a REST API for integration into existing tooling

---

## Target Users

- **Platform / SRE Teams** — own runbooks, care about on-call reliability
- **Engineering Managers** — want doc health metrics across teams
- **DevOps Engineers** — integrate with CI/CD and infra tooling
- **Tech Leads** — maintain service ownership and onboarding docs

---

## Success Metrics

- % of runbooks with a reliability score ≥ 80
- Number of drift alerts caught before an incident
- Time from drift occurrence to alert delivery (target: < 24h)
- Runbook coverage per service (services with 0 docs)
- Monthly active API consumers

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| ORM | SQLAlchemy / SQLModel |
| Database | PostgreSQL |
| Background Jobs | Celery or Arq |
| Migrations | Alembic |
| HTTP Client | httpx |
| Data Validation | Pydantic |
| NLP / Entity Extraction | spaCy or custom regex pipelines |
| Optional (future) | pgvector for semantic search |

---

## Core Modules

| Module | Responsibility |
|---|---|
| `ingestion-service` | Pull and parse docs from all sources |
| `entity-extraction-service` | Extract structured entities from raw doc text |
| `drift-rules-engine` | Compare entities vs live infra state |
| `evidence-store` | Persist raw evidence from live systems |
| `alerting-service` | Deliver alerts via Slack / email / webhook |
| `scoring-service` | Compute per-runbook reliability confidence scores |
| `REST API` | Expose findings, scores, and triggers externally |

---

## Phased Roadmap

### Phase 1 — Foundation (Weeks 1–3)
- DB schema, migrations, core models
- Document ingestion (Markdown + Git)
- Basic entity extraction pipeline
- REST API skeleton

### Phase 2 — Intelligence (Weeks 4–6)
- Drift rules engine (5 core rule types)
- Evidence store from GitHub + one infra source
- Reliability scoring algorithm
- Nightly scan job (Celery/Arq)

### Phase 3 — Alerting & Output (Weeks 7–8)
- Slack webhook output
- Email digest
- Audit report API endpoint
- Per-service findings endpoint

### Phase 4 — Expansion (Post-MVP)
- Confluence + Notion ingestion
- Kubernetes + AWS + PagerDuty connectors
- pgvector semantic search
- Dashboard UI (optional)
- Multi-tenant support

---

## Constraints & Assumptions

- MVP is backend-only — no frontend required
- Authentication handled via API keys (simple, ship fast)
- Drift rules are configurable per workspace
- All integrations are read-only (no writes to connected systems)
