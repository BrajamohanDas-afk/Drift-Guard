# Nightly Scan Load Test

> UPDATED 2026-05-13: Added a local load-test path for Phase 9.

## Goal

Validate that `nightly_scan` can enumerate configured sources and enqueue ingest
jobs without overwhelming Redis or the worker queue.

## Prerequisites

Start local services and run migrations:

```powershell
docker compose up -d --build app worker postgres redis
docker compose exec app uv run alembic upgrade head
```

Create a few Git sources through Swagger or the API. If there are no sources,
the scan will return `completed_no_sources`.

## Run From The Worker Container

```powershell
docker compose exec worker uv run python scripts/load_test_nightly_scan.py --iterations 5
```

Use `--fail-fast` if you want the first failed scan to stop the run:

```powershell
docker compose exec worker uv run python scripts/load_test_nightly_scan.py --iterations 5 --fail-fast
```

## Pass Criteria

- the script exits with code `0`
- each iteration returns `queued`, `queued_with_errors`, or `completed_no_sources`
- Redis does not hit the configured queue depth limit
- worker logs do not show repeated enqueue failures

## Follow-Up Checks

```powershell
docker compose logs --tail=200 worker
docker compose exec postgres psql -U drift -d driftguard -c "select status, count(*) from audit_jobs group by status order by status;"
```
