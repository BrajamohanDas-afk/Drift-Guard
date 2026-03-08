# Runbook Drift Radar — User Journeys

> Because Drift Radar is a backend/API product, "users" are primarily engineers and platform teams interacting via API, CLI, or integrated tooling. Each journey maps the steps, API calls, and system behavior end-to-end.

---

## Personas

### Alex — SRE / Platform Engineer
Owns the on-call runbooks. Tired of discovering bad docs at 3am. Wants automated confidence metrics for every runbook before an incident happens.

### Jordan — Engineering Manager
Wants a weekly report on doc health across all services their teams own. Doesn't want to manually audit 40 runbooks.

### Sam — DevOps Engineer
Connecting Drift Radar to GitHub and Kubernetes as part of the internal platform stack. Wants reliable integrations and clear API docs.

---

## Journey 1: First Setup (Sam — DevOps Engineer)

**Goal:** Get Drift Radar connected and scanning a team's runbooks within 30 minutes.

### Steps

**1. Deploy the service**
```
docker compose up -d
# App running at http://localhost:8000
# Postgres + Redis up
```

**2. Connect a Git source (where runbooks live)**
```http
POST /v1/sources
{
  "name": "Platform Runbooks Repo",
  "type": "git",
  "config": {
    "repo_url": "https://github.com/acme/runbooks",
    "token": "ghp_xxxxx",
    "branch": "main",
    "path_filter": "docs/runbooks/"
  }
}
→ 201 Created { "id": "src-001" }
```

**3. Trigger initial sync**
```http
POST /v1/sources/src-001/sync
→ 202 Accepted { "audit_job_id": "job-001" }
```

**4. Poll for job completion**
```http
GET /v1/audit/jobs/job-001
→ { "status": "complete", "docs_scanned": 14, "alerts_created": 7 }
```

**5. Review first findings**
```http
GET /v1/alerts?severity=critical
→ List of critical drift alerts with evidence
```

**Outcome:** Sam sees 14 runbooks scanned, 7 drift alerts surfaced. Shares findings with Alex.

---

## Journey 2: Reviewing a Runbook's Health (Alex — SRE)

**Goal:** Understand exactly why a specific runbook is scoring low and what needs to be fixed.

### Steps

**1. List all documents with scores**
```http
GET /v1/scores
→ [
    { "document_id": "doc-042", "title": "payments-api-recovery.md", "score": 38, "band": "Critical" },
    { "document_id": "doc-017", "title": "auth-service-runbook.md", "score": 91, "band": "Healthy" },
    ...
  ]
```

**2. Inspect the low-scoring runbook**
```http
GET /v1/scores/doc-042
→ {
    "score": 38,
    "breakdown": {
      "critical_alerts": 2,
      "warning_alerts": 3,
      "deductions": {
        "critical": -40,
        "warning": -16,
        "stale_doc": -10
      }
    }
  }
```

**3. Pull the alerts for that document**
```http
GET /v1/alerts?document_id=doc-042
→ [
    {
      "rule_type": "owner_missing",
      "severity": "critical",
      "message": "Owner '@dave' not found in CODEOWNERS or PagerDuty",
      "evidence": { "searched_in": ["github_codeowners", "pagerduty"], "result": "not_found" }
    },
    {
      "rule_type": "dashboard_dead",
      "severity": "critical",
      "message": "Dashboard URL returned 404",
      "evidence": { "url": "https://grafana.internal/d/old-payments", "status_code": 404 }
    },
    {
      "rule_type": "command_deprecated",
      "severity": "warning",
      "message": "Script referenced in runbook no longer exists in repo",
      "evidence": { "command": "scripts/rollback-v1.sh", "checked_at_commit": "a3f9c2d" }
    }
  ]
```

**4. Alex fixes the runbook, pushes to Git**

**5. Alex triggers a re-scan**
```http
POST /v1/audit/run
→ 202 Accepted
```

**6. Resolves fixed alerts and watches score improve**
```http
PATCH /v1/alerts/alert-007/resolve
GET /v1/scores/doc-042
→ { "score": 79, "band": "Degraded" }
```

**Outcome:** Alex has a clear action list, fixes two issues, and sees the score recover.

---

## Journey 3: Weekly Team Report (Jordan — Engineering Manager)

**Goal:** Get a summary of all runbook health across the payments team's services, every Monday.

### Steps

**1. Jordan sets up a scheduled webhook (via config)**
```yaml
# drift-radar config
alerts:
  weekly_digest:
    enabled: true
    day: monday
    time: "09:00"
    channel: slack
    webhook_url: "https://hooks.slack.com/services/xxx"
    filter:
      service_team: payments
```

**2. Every Monday, Drift Radar sends to Slack:**
```
📊 Weekly Runbook Health — Payments Team
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Healthy (≥80):     6 runbooks
⚠️  Degraded (60–79): 3 runbooks
🔴 Critical (<60):    2 runbooks

New alerts this week: 4
Resolved alerts:      2

Worst performer: payments-api-recovery.md (score: 38)
Services with no runbook: 1 (fraud-detection-v2)

→ Full report: http://drift-radar.internal/v1/audit/report
```

**3. Jordan can also pull the report on demand:**
```http
GET /v1/audit/report?team=payments&format=json
→ Full breakdown per service + runbook
```

**Outcome:** Jordan gets signal every Monday without touching a runbook manually.

---

## Journey 4: CI/CD Integration (Sam — DevOps)

**Goal:** Block merges to the `runbooks/` folder if the resulting doc would score below 60.

### Steps

**1. GitHub Actions workflow triggers on PR to `docs/runbooks/**`**

**2. CI uploads the changed doc to Drift Radar**
```http
POST /v1/documents/upload
Content-Type: multipart/form-data
file: payments-api-recovery.md
→ { "document_id": "doc-preview-123" }
```

**3. CI triggers a scan on just that document**
```http
POST /v1/audit/run?document_id=doc-preview-123
→ 202 Accepted { "audit_job_id": "job-preview-007" }
```

**4. CI polls until complete, then checks score**
```http
GET /v1/scores/doc-preview-123
→ { "score": 42, "band": "Critical" }
```

**5. If score < 60, CI fails the PR with a comment:**
```
❌ Runbook reliability score: 42/100 (Critical)
Issues found:
  - Owner '@dave' not found in PagerDuty
  - Dashboard URL returns 404
Fix these before merging.
```

**Outcome:** Bad runbooks are caught at PR time, not at incident time.

---

## Journey 5: New Service Has No Runbook (Dependency Alert)

**Goal:** Detect when a new service is deployed to production but has zero documentation.

### Steps

**1. Nightly scan runs. Kubernetes collector pulls service list.**

**2. Drift rules engine runs `dependency_undocumented` rule:**
- Finds `fraud-detection-v2` running in `prod-us-east-1`
- Searches `documents` table for any doc mentioning `fraud-detection-v2`
- No match found

**3. Alert is created:**
```json
{
  "rule_type": "dependency_undocumented",
  "severity": "warning",
  "message": "Service 'fraud-detection-v2' is running in prod but has no runbook",
  "evidence": {
    "found_in": "kubernetes/prod-us-east-1",
    "namespace": "production",
    "replicas": 3
  }
}
```

**4. Alert appears in Monday digest to Jordan and in the API:**
```http
GET /v1/audit/service/fraud-detection-v2
→ { "runbooks": [], "alerts": [{ "type": "dependency_undocumented" }], "score": null }
```

**Outcome:** Team is alerted that a production service is undocumented — before an incident forces someone to figure it out under pressure.

---

## Error States & Edge Cases

| Situation | System Behavior |
|---|---|
| GitHub API rate-limited during scan | Pause, retry with backoff, continue with other rules |
| Dashboard URL times out | Recorded as `inconclusive`, not a failed alert |
| Doc has no extractable entities | Score penalized, `info` alert raised |
| Source sync fails mid-way | Partial results saved, `audit_job.status = partial` |
| Same alert would be created twice | Deduplicated — existing unresolved alert updated |
| Manual scan triggered while nightly running | Queued, runs after current job completes |
