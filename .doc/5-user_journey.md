# Drift Guard - User Journeys

> UPDATED 2026-03-30: These journeys now match the features that actually exist in the repository today. Future journeys are called out separately.

## Personas

### Sam - DevOps Engineer

Connects runbook sources and validates that ingestion works.

### Alex - SRE / Platform Engineer

Uploads runbooks directly and expects entities to be extracted correctly.

### Jordan - Engineering Manager

Will care about scores and reports later, but those flows are not implemented yet.

## Journey 1 - First Local Bring-Up

**Goal:** get the service running and confirm the API is alive.

### Steps

1. Start dependencies and app.

```powershell
docker compose up -d --build app postgres redis
```

2. Run migrations.

```powershell
docker compose exec app uv run alembic upgrade head
```

3. Verify the service.

```http
GET /health
```

Expected response:

```json
{"status":"ok"}
```

### Outcome

The service is reachable and ready for authenticated document and source operations.

## Journey 2 - Upload A Runbook Directly

**Goal:** create a document, version it, and extract entities from it.

### Steps

1. Send an authenticated upload request.

```http
POST /v1/documents/upload
Header: X-API-Key: <api-key>
Content-Type: multipart/form-data
file: payments.md
```

2. Drift Guard:

- creates a source-less `documents` row if needed
- hashes the content
- creates a new `document_version` only when content changed
- normalizes the Markdown
- extracts supported entity types

3. List documents.

```http
GET /v1/documents
Header: X-API-Key: <api-key>
```

4. Fetch the specific document.

```http
GET /v1/documents/{document_id}
Header: X-API-Key: <api-key>
```

### Outcome

Alex can confirm that the document exists and that repeated uploads behave like versioned updates instead of duplicate records.

## Journey 3 - Sync A GitHub Runbook Source

**Goal:** create a Git source and ingest Markdown files from GitHub.

### Steps

1. Create the source.

```http
POST /v1/sources
Header: X-API-Key: <api-key>
Content-Type: application/json

{
  "name": "Platform Runbooks",
  "type": "git",
  "config": {
    "repo_url": "https://github.com/acme/runbooks",
    "branch": "main",
    "path_filter": "docs/runbooks"
  }
}
```

2. Trigger sync.

```http
POST /v1/sources/{source_id}/sync
Header: X-API-Key: <api-key>
```

3. Drift Guard:

- fetches Markdown files recursively from GitHub
- identifies source-backed documents by `source_id + path`
- creates or updates `document_versions`
- extracts entities for each changed file

4. Review the sync summary returned by the endpoint.

### Outcome

Sam can ingest a repository of Markdown runbooks without collapsing same-named files from different folders into the same document.

## Journey 4 - Remove A Document From Active Listings

**Goal:** archive a document without deleting historical versions.

### Steps

1. Delete the document through the API.

```http
DELETE /v1/documents/{document_id}
Header: X-API-Key: <api-key>
```

2. Try to fetch the same document again.

```http
GET /v1/documents/{document_id}
Header: X-API-Key: <api-key>
```

Expected result:

- delete succeeds
- follow-up `GET` returns `404`
- the document no longer appears in normal list results

### Outcome

The document is archived from active use while version history remains in the database.

## Future Journeys - Not Implemented Yet

The following product journeys are still planned only:

- reviewing generated alerts
- resolving alerts
- reading per-document reliability scores
- triggering tracked audit jobs
- consuming JSON audit reports
- receiving Slack or email notifications
- blocking CI on low runbook reliability

These should stay documented as future-state until the corresponding API routes and services are implemented.
