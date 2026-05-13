# Phase 9 Observability Runbook

> UPDATED 2026-05-13: Added the free/local observability path for Phase 9.

## Scope

This project does not require paid monitoring SaaS for the current milestone.
The Phase 9 baseline is:

- structured application logs
- request-level logging with `x-request-id`
- worker lifecycle and task result logs
- Docker health checks for Postgres and Redis
- local inspection commands for failures and queue pressure

## Request Logs

Every HTTP request gets an `x-request-id` response header. If the caller sends an
`x-request-id`, the app preserves it. Logs include:

- request id
- method
- path without query string
- status code
- client host
- duration in milliseconds

Queries and auth headers are intentionally not logged.

## Local Commands

Inspect app logs:

```powershell
docker compose logs --tail=200 app
```

Inspect worker logs:

```powershell
docker compose logs --tail=200 worker
```

Follow both while testing:

```powershell
docker compose logs -f app worker
```

Check service health:

```powershell
docker compose ps
curl http://localhost:8000/health
```

Check recent failed notification deliveries:

```powershell
docker compose exec postgres psql -U drift -d driftguard -c "select event_type, channel, status, attempts, error, created_at from notification_deliveries where status = 'failed' order by created_at desc limit 20;"
```

Check recent failed audit jobs:

```powershell
docker compose exec postgres psql -U drift -d driftguard -c "select id, status, error, started_at, completed_at from audit_jobs where status = 'failed' order by started_at desc limit 20;"
```

## Alert Conditions

For a self-hosted deployment, alert on:

- `/health` not returning `200`
- repeated `request failed` logs
- repeated `QueueCapacityError` or queue capacity warnings
- failed audit jobs
- failed notification deliveries
- Redis or Postgres health checks failing

These can be wired to any free/self-hosted log collector later. The app-side
contract is the structured log fields and persisted failure rows.
