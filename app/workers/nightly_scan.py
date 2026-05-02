import datetime
import logging
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.source import Source
from app.workers.queue import QueueEnqueueError, enqueue_ingest_task, get_redis_pool

logger = logging.getLogger(__name__)


async def _list_source_ids() -> list[str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Source.id).order_by(Source.created_at.asc(), Source.id.asc())
        )
        return [str(source_id) for source_id in result.scalars().all()]


async def nightly_scan(_ctx: dict[str, Any]) -> dict[str, Any]:
    scan_started_at = datetime.datetime.now(datetime.timezone.utc)
    source_ids = await _list_source_ids()
    if not source_ids:
        logger.info("Nightly scan skipped because no sources were found")
        return {
            "status": "completed_no_sources",
            "scan_run_id": None,
            "scan_started_at": scan_started_at.isoformat(),
            "sources_seen": 0,
            "jobs_enqueued": 0,
            "jobs_skipped": 0,
            "failed_sources": [],
        }

    redis = await get_redis_pool()
    scan_run_id = scan_started_at.strftime("%Y%m%d")
    jobs_enqueued = 0
    jobs_skipped = 0
    failed_sources: list[str] = []

    try:
        for source_id in source_ids:
            try:
                job = await enqueue_ingest_task(
                    source_id=source_id,
                    redis=redis,
                    job_id=f"nightly-ingest:{scan_run_id}:{source_id}",
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue nightly ingest task",
                    extra={"source_id": source_id},
                )
                failed_sources.append(source_id)
                continue

            if job is None:
                jobs_skipped += 1
            else:
                jobs_enqueued += 1
    finally:
        try:
            await redis.close(close_connection_pool=True)
        except Exception:
            logger.warning(
                "Failed to close Redis pool after nightly scan",
                exc_info=True,
            )

    summary = {
        "status": "queued_with_errors" if failed_sources else "queued",
        "scan_run_id": scan_run_id,
        "scan_started_at": scan_started_at.isoformat(),
        "sources_seen": len(source_ids),
        "jobs_enqueued": jobs_enqueued,
        "jobs_skipped": jobs_skipped,
        "failed_sources": failed_sources,
    }
    if failed_sources:
        logger.error("Nightly scan finished with enqueue failures", extra=summary)
        raise QueueEnqueueError(
            f"Nightly scan enqueue failed for {len(failed_sources)} source(s)"
        )

    logger.info("Nightly scan finished", extra=summary)
    return summary
