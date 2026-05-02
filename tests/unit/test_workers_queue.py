import pytest

from app.workers.common import WORKER_QUEUE_NAME
from app.workers.queue import (
    QueueEnqueueError,
    enqueue_audit_run_task,
    enqueue_ingest_task,
    enqueue_nightly_scan,
    enqueue_score_task,
    get_redis_pool,
)


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeRedis:
    def __init__(self, *, fail_enqueue: bool = False, fail_close: bool = False):
        self.fail_enqueue = fail_enqueue
        self.fail_close = fail_close
        self.enqueue_calls = []
        self.closed = False
        self.close_connection_pool = None
        self.job = object()

    async def enqueue_job(self, function_name, **kwargs):
        self.enqueue_calls.append((function_name, kwargs))
        if self.fail_enqueue:
            raise RuntimeError("enqueue failed")
        return self.job

    async def close(self, *, close_connection_pool: bool):
        if self.fail_close:
            raise RuntimeError("close failed")
        self.closed = True
        self.close_connection_pool = close_connection_pool


@pytest.mark.asyncio
async def test_enqueue_ingest_task_uses_worker_queue_and_closes_owned_pool(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = _FakeRedis()

    async def fake_get_pool():
        return fake_redis

    monkeypatch.setattr("app.workers.queue.get_redis_pool", fake_get_pool)

    result = await enqueue_ingest_task(
        source_id="source-1",
        audit_job_id="audit-1",
        job_id="job-1",
    )

    assert result is fake_redis.job
    assert fake_redis.enqueue_calls == [
        (
            "ingest_task",
            {
                "_job_id": "job-1",
                "_queue_name": WORKER_QUEUE_NAME,
                "_defer_until": None,
                "_defer_by": None,
                "_expires": None,
                "source_id": "source-1",
                "audit_job_id": "audit-1",
            },
        )
    ]
    assert fake_redis.closed is True
    assert fake_redis.close_connection_pool is True


@pytest.mark.asyncio
async def test_enqueue_audit_run_task_uses_expected_function_name():
    fake_redis = _FakeRedis()

    result = await enqueue_audit_run_task(
        audit_job_id="audit-1",
        redis=fake_redis,
        job_id="audit-run:audit-1",
    )

    assert result is fake_redis.job
    assert fake_redis.enqueue_calls == [
        (
            "audit_run_task",
            {
                "_job_id": "audit-run:audit-1",
                "_queue_name": WORKER_QUEUE_NAME,
                "_defer_until": None,
                "_defer_by": None,
                "_expires": None,
                "audit_job_id": "audit-1",
            },
        )
    ]
    assert fake_redis.closed is False


@pytest.mark.asyncio
async def test_enqueue_score_task_with_injected_pool_does_not_close_pool():
    fake_redis = _FakeRedis()

    result = await enqueue_score_task(
        document_id="doc-1",
        audit_job_id="audit-1",
        redis=fake_redis,
    )

    assert result is fake_redis.job
    assert fake_redis.enqueue_calls[0][0] == "score_task"
    assert fake_redis.enqueue_calls[0][1]["_queue_name"] == WORKER_QUEUE_NAME
    assert fake_redis.enqueue_calls[0][1]["document_id"] == "doc-1"
    assert fake_redis.enqueue_calls[0][1]["audit_job_id"] == "audit-1"
    assert fake_redis.closed is False


@pytest.mark.asyncio
async def test_enqueue_nightly_scan_uses_expected_function_name(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = _FakeRedis()

    async def fake_get_pool():
        return fake_redis

    monkeypatch.setattr("app.workers.queue.get_redis_pool", fake_get_pool)

    await enqueue_nightly_scan(job_id="nightly-1")

    assert fake_redis.enqueue_calls[0][0] == "nightly_scan"
    assert fake_redis.enqueue_calls[0][1]["_job_id"] == "nightly-1"
    assert fake_redis.enqueue_calls[0][1]["_queue_name"] == WORKER_QUEUE_NAME


@pytest.mark.asyncio
async def test_enqueue_wraps_errors_in_queue_enqueue_error(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = _FakeRedis(fail_enqueue=True)

    async def fake_get_pool():
        return fake_redis

    monkeypatch.setattr("app.workers.queue.get_redis_pool", fake_get_pool)

    with pytest.raises(QueueEnqueueError, match="failed to enqueue job 'ingest_task'"):
        await enqueue_ingest_task(source_id="source-1")

    assert fake_redis.closed is True


@pytest.mark.asyncio
async def test_enqueue_with_injected_pool_wraps_enqueue_failures_without_closing_pool():
    fake_redis = _FakeRedis(fail_enqueue=True)

    with pytest.raises(QueueEnqueueError, match="failed to enqueue job 'ingest_task'"):
        await enqueue_ingest_task(source_id="source-1", redis=fake_redis)

    assert fake_redis.closed is False


@pytest.mark.asyncio
async def test_get_redis_pool_wraps_create_pool_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_create_pool(_settings):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.workers.queue.create_pool", fake_create_pool)

    with pytest.raises(QueueEnqueueError, match="failed to create redis pool"):
        await get_redis_pool()


@pytest.mark.asyncio
async def test_enqueue_does_not_mask_success_when_close_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_redis = _FakeRedis(fail_close=True)

    async def fake_get_pool():
        return fake_redis

    monkeypatch.setattr("app.workers.queue.get_redis_pool", fake_get_pool)

    result = await enqueue_ingest_task(source_id="source-1")

    assert result is fake_redis.job
