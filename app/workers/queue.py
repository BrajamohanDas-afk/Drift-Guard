import datetime
import logging
from typing import Any

from arq.connections import ArqRedis, create_pool
from arq.jobs import Job

from app.config import settings
from app.workers.common import WORKER_QUEUE_NAME, redis_settings_from_url

logger = logging.getLogger(__name__)


class QueueEnqueueError(RuntimeError):
    pass


async def get_redis_pool() -> ArqRedis:
    redis_settings = redis_settings_from_url(settings.redis_url)
    try:
        return await create_pool(redis_settings)
    except Exception as exc:
        logger.exception("Failed to create Redis pool for worker queue")
        raise QueueEnqueueError("failed to create redis pool") from exc


async def _enqueue_job(
    function_name: str,
    *,
    redis: ArqRedis | None = None,
    job_id: str | None = None,
    defer_until: datetime.datetime | None = None,
    defer_by: datetime.timedelta | int | float | None = None,
    expires: datetime.timedelta | int | float | None = None,
    **kwargs: Any,
) -> Job | None:
    owned_pool = False
    pool = redis
    if pool is None:
        pool = await get_redis_pool()
        owned_pool = True

    try:
        return await pool.enqueue_job(
            function_name,
            _job_id=job_id,
            _queue_name=WORKER_QUEUE_NAME,
            _defer_until=defer_until,
            _defer_by=defer_by,
            _expires=expires,
            **kwargs,
        )
    except Exception as exc:
        logger.exception(
            "Failed to enqueue worker job",
            extra={
                "function_name": function_name,
                "queue_name": WORKER_QUEUE_NAME,
                "job_id": job_id,
            },
        )
        raise QueueEnqueueError(f"failed to enqueue job '{function_name}'") from exc
    finally:
        if owned_pool:
            try:
                await pool.close(close_connection_pool=True)
            except Exception:
                logger.warning(
                    "Failed to close owned Redis pool after enqueue",
                    extra={"function_name": function_name},
                    exc_info=True,
                )


async def enqueue_ingest_task(
    *,
    source_id: str,
    audit_job_id: str | None = None,
    redis: ArqRedis | None = None,
    job_id: str | None = None,
    defer_until: datetime.datetime | None = None,
    defer_by: datetime.timedelta | int | float | None = None,
    expires: datetime.timedelta | int | float | None = None,
) -> Job | None:
    return await _enqueue_job(
        "ingest_task",
        redis=redis,
        job_id=job_id,
        defer_until=defer_until,
        defer_by=defer_by,
        expires=expires,
        source_id=source_id,
        audit_job_id=audit_job_id,
    )


async def enqueue_audit_run_task(
    *,
    audit_job_id: str,
    redis: ArqRedis | None = None,
    job_id: str | None = None,
    defer_until: datetime.datetime | None = None,
    defer_by: datetime.timedelta | int | float | None = None,
    expires: datetime.timedelta | int | float | None = None,
) -> Job | None:
    return await _enqueue_job(
        "audit_run_task",
        redis=redis,
        job_id=job_id,
        defer_until=defer_until,
        defer_by=defer_by,
        expires=expires,
        audit_job_id=audit_job_id,
    )


async def enqueue_score_task(
    *,
    document_id: str,
    audit_job_id: str | None = None,
    redis: ArqRedis | None = None,
    job_id: str | None = None,
    defer_until: datetime.datetime | None = None,
    defer_by: datetime.timedelta | int | float | None = None,
    expires: datetime.timedelta | int | float | None = None,
) -> Job | None:
    return await _enqueue_job(
        "score_task",
        redis=redis,
        job_id=job_id,
        defer_until=defer_until,
        defer_by=defer_by,
        expires=expires,
        document_id=document_id,
        audit_job_id=audit_job_id,
    )


async def enqueue_nightly_scan(
    *,
    redis: ArqRedis | None = None,
    job_id: str | None = None,
    defer_until: datetime.datetime | None = None,
    defer_by: datetime.timedelta | int | float | None = None,
    expires: datetime.timedelta | int | float | None = None,
) -> Job | None:
    return await _enqueue_job(
        "nightly_scan",
        redis=redis,
        job_id=job_id,
        defer_until=defer_until,
        defer_by=defer_by,
        expires=expires,
    )
