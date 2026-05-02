import importlib

import pytest

from app.workers.queue import QueueEnqueueError

nightly_scan_module = importlib.import_module("app.workers.nightly_scan")


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeRedis:
    def __init__(self, *, fail_close: bool = False):
        self.fail_close = fail_close
        self.closed = False
        self.close_connection_pool = None

    async def close(self, *, close_connection_pool: bool):
        if self.fail_close:
            raise RuntimeError("close failed")
        self.closed = True
        self.close_connection_pool = close_connection_pool


@pytest.mark.asyncio
async def test_nightly_scan_enqueues_all_sources(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeRedis()
    calls: list[tuple[str, str]] = []

    async def fake_list_source_ids():
        return ["source-a", "source-b"]

    async def fake_get_redis_pool():
        return fake_redis

    async def fake_enqueue_ingest_task(*, source_id, redis, job_id, **_kwargs):
        calls.append((source_id, job_id))
        assert redis is fake_redis
        return object()

    monkeypatch.setattr(nightly_scan_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(nightly_scan_module, "get_redis_pool", fake_get_redis_pool)
    monkeypatch.setattr(
        nightly_scan_module, "enqueue_ingest_task", fake_enqueue_ingest_task
    )

    result = await nightly_scan_module.nightly_scan({})
    expected_run_id = result["scan_started_at"][:10].replace("-", "")

    assert result["status"] == "queued"
    assert result["scan_run_id"] == expected_run_id
    assert result["scan_started_at"]
    assert result["sources_seen"] == 2
    assert result["jobs_enqueued"] == 2
    assert result["jobs_skipped"] == 0
    assert result["failed_sources"] == []
    assert calls == [
        ("source-a", f"nightly-ingest:{expected_run_id}:source-a"),
        ("source-b", f"nightly-ingest:{expected_run_id}:source-b"),
    ]
    assert fake_redis.closed is True
    assert fake_redis.close_connection_pool is True


@pytest.mark.asyncio
async def test_nightly_scan_counts_skipped_jobs(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeRedis()

    async def fake_list_source_ids():
        return ["source-a"]

    async def fake_get_redis_pool():
        return fake_redis

    async def fake_enqueue_ingest_task(*, source_id, redis, job_id, **_kwargs):
        assert source_id == "source-a"
        assert redis is fake_redis
        assert job_id.startswith("nightly-ingest:")
        assert job_id.endswith(":source-a")
        return None

    monkeypatch.setattr(nightly_scan_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(nightly_scan_module, "get_redis_pool", fake_get_redis_pool)
    monkeypatch.setattr(
        nightly_scan_module, "enqueue_ingest_task", fake_enqueue_ingest_task
    )

    result = await nightly_scan_module.nightly_scan({})
    expected_run_id = result["scan_started_at"][:10].replace("-", "")

    assert result["status"] == "queued"
    assert result["scan_run_id"] == expected_run_id
    assert result["scan_started_at"]
    assert result["jobs_enqueued"] == 0
    assert result["jobs_skipped"] == 1
    assert result["failed_sources"] == []
    assert fake_redis.closed is True


@pytest.mark.asyncio
async def test_nightly_scan_handles_enqueue_failures(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeRedis()

    async def fake_list_source_ids():
        return ["source-a", "source-b"]

    async def fake_get_redis_pool():
        return fake_redis

    async def fake_enqueue_ingest_task(*, source_id, **_kwargs):
        if source_id == "source-a":
            raise QueueEnqueueError("enqueue failed")
        return object()

    monkeypatch.setattr(nightly_scan_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(nightly_scan_module, "get_redis_pool", fake_get_redis_pool)
    monkeypatch.setattr(
        nightly_scan_module, "enqueue_ingest_task", fake_enqueue_ingest_task
    )

    with pytest.raises(QueueEnqueueError, match="Nightly scan enqueue failed"):
        await nightly_scan_module.nightly_scan({})

    assert fake_redis.closed is True


@pytest.mark.asyncio
async def test_nightly_scan_wraps_unexpected_enqueue_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = _FakeRedis()

    async def fake_list_source_ids():
        return ["source-a"]

    async def fake_get_redis_pool():
        return fake_redis

    async def fake_enqueue_ingest_task(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(nightly_scan_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(nightly_scan_module, "get_redis_pool", fake_get_redis_pool)
    monkeypatch.setattr(
        nightly_scan_module, "enqueue_ingest_task", fake_enqueue_ingest_task
    )

    with pytest.raises(QueueEnqueueError, match="Nightly scan enqueue failed"):
        await nightly_scan_module.nightly_scan({})

    assert fake_redis.closed is True


@pytest.mark.asyncio
async def test_nightly_scan_propagates_redis_pool_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_list_source_ids():
        return ["source-a"]

    async def fake_get_redis_pool():
        raise QueueEnqueueError("pool unavailable")

    monkeypatch.setattr(nightly_scan_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(nightly_scan_module, "get_redis_pool", fake_get_redis_pool)

    with pytest.raises(QueueEnqueueError, match="pool unavailable"):
        await nightly_scan_module.nightly_scan({})


@pytest.mark.asyncio
async def test_nightly_scan_returns_empty_summary_without_sources(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_list_source_ids():
        return []

    async def fail_get_redis_pool():
        raise AssertionError(
            "get_redis_pool should not be called when no sources exist"
        )

    monkeypatch.setattr(nightly_scan_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(nightly_scan_module, "get_redis_pool", fail_get_redis_pool)

    result = await nightly_scan_module.nightly_scan({})

    assert result["status"] == "completed_no_sources"
    assert result["scan_run_id"] is None
    assert result["scan_started_at"]
    assert result["sources_seen"] == 0
    assert result["jobs_enqueued"] == 0
    assert result["jobs_skipped"] == 0
    assert result["failed_sources"] == []


@pytest.mark.asyncio
async def test_nightly_scan_does_not_fail_when_close_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = _FakeRedis(fail_close=True)

    async def fake_list_source_ids():
        return ["source-a"]

    async def fake_get_redis_pool():
        return fake_redis

    async def fake_enqueue_ingest_task(**_kwargs):
        return object()

    monkeypatch.setattr(nightly_scan_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(nightly_scan_module, "get_redis_pool", fake_get_redis_pool)
    monkeypatch.setattr(
        nightly_scan_module, "enqueue_ingest_task", fake_enqueue_ingest_task
    )

    result = await nightly_scan_module.nightly_scan({})

    assert result["status"] == "queued"
    assert result["jobs_enqueued"] == 1
