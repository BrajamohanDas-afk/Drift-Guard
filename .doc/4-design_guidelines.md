# Drift Guard - Design Guidelines

> UPDATED 2026-03-30: These guidelines now separate enforced current behavior from target architecture so the docs do not overstate what the code already does.

## Core Principles

### 1. Backend First

Drift Guard remains an API-first backend. No planned work should depend on a frontend existing.

### 2. Evidence Before Judgment

Do not generate drift alerts from guesswork. A drift rule should only emit an alert when it can attach concrete evidence.

### 3. Idempotent Ingestion

This is already partly enforced today:

- uploads skip new versions when content hash is unchanged
- source sync reuses the same source-backed document identity

Keep all future ingestion work idempotent as well.

### 4. Version-Scoped Auditability

This is already enforced in the current schema and ingestion code:

- document content lives in `document_versions`
- extracted entities point to `document_version_id`
- source-backed documents are identified by `source_id + path`

Do not regress this model.

### 5. Read-Only Integrations

All external integrations must stay read-only. Drift Guard should observe and report, not mutate external systems.

## Integration Standards

### Optional Integration Degradation

External evidence integrations (for example PagerDuty and Kubernetes) must be optional.

If credentials are missing:

- collectors must return structured evidence with a clear configuration error
- collectors must not raise unhandled exceptions
- development and unit testing must remain runnable with mocked responses

## API Design Rules

### Current State

The live API is mixed right now:

- list endpoints use `data` plus `meta`
- singular document and source creation responses return direct resource models
- source sync returns a custom `data` payload

Do not document a uniform envelope as if it already exists. If the team wants one response shape later, treat it as an explicit API refactor.

### Versioning

Keep endpoints under `/v1/`.

### Authentication

Current enforced behavior:

- document routes require `X-API-Key`
- source routes require `X-API-Key`

Future rule:

- when alerts, scores, and audit endpoints are implemented, they should use the same API key dependency unless the auth model is upgraded across the app in one coordinated change

### Status Codes

Use:

- `200` for reads and standard mutations
- `201` for resource creation
- `202` only for true async work
- `400` for bad input
- `401` for missing or invalid API key
- `404` for missing resources

Important: the current source sync endpoint returns `202` even though it executes inline. That should be fixed when background jobs are introduced.

## Data Modeling Rules

### UUID Primary Keys

Keep UUIDs for all major entities.

### JSONB For Flexible Payloads

Current appropriate JSONB fields:

- `sources.config`
- `alerts.evidence`
- `runbook_scores.breakdown`

### Soft Delete Semantics

Current implemented rule:

- documents are soft-deleted via `is_deleted` and `deleted_at`
- deleted documents are excluded from normal list/get behavior

Future rule:

- alerts should also preserve history through resolution rather than deletion

## Extraction Rules

### Deterministic Extraction

Keep extraction regex-based and deterministic for now. The current extraction layer should remain predictable and testable.

### Supported Entity Types Today

- `service`
- `owner`
- `url`
- `dashboard`
- `command`
- `env_var`
- `iam_role`
- `helm_chart`
- `cluster`

### Extraction Contract

The extraction pipeline should continue to:

1. normalize text
2. run each extractor
3. deduplicate repeated entity values within the same ingest pass
4. persist entities against a specific document version

## Drift Engine Rules

These are target rules, not current implementation:

- rule classes should be isolated units
- rules should accept structured evidence, not perform uncontrolled side effects
- alert creation should be deduplicated
- unresolved identical alerts should not be recreated repeatedly

## Scoring Rules

Scoring is still future work, but the intended contract is:

- calculate a per-document reliability score
- store the numeric result plus structured breakdown
- expose both summary and per-document detail through the API

Do not mark scoring complete until those three parts all exist.

## Job Design Rules

The repo already has worker files and an `AuditJob` model, but not a real job system.

When jobs are implemented:

- use `AuditJob` as the source of truth for execution status
- return real job ids from async endpoints
- keep audit runs resumable or at least inspectable after failure

## Documentation Rules

Planning documents in `.doc/` must be treated as live status documents.

Each update should:

- state when the file was reconciled
- distinguish implemented behavior from future intent
- avoid claiming roadmap phases are complete unless code and tests support the claim
