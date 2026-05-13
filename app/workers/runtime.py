import datetime
import logging
from typing import Any

from arq import cron

from app.config import settings
from app.workers.audit_run_task import audit_run_task
from app.workers.common import WORKER_QUEUE_NAME, redis_settings_from_url
from app.workers.ingest_task import ingest_task
from app.workers.nightly_scan import nightly_scan
from app.workers.notification_task import notification_task
from app.workers.score_task import score_task

logger = logging.getLogger(__name__)


def _validate_cron_component(
    name: str, value: int, *, minimum: int, maximum: int
) -> None:
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def build_cron_jobs() -> list:
    if not settings.nightly_scan_cron_enabled:
        return []

    _validate_cron_component(
        "NIGHTLY_SCAN_CRON_HOUR_UTC",
        settings.nightly_scan_cron_hour_utc,
        minimum=0,
        maximum=23,
    )
    _validate_cron_component(
        "NIGHTLY_SCAN_CRON_MINUTE",
        settings.nightly_scan_cron_minute,
        minimum=0,
        maximum=59,
    )

    return [
        cron(
            nightly_scan,
            name="nightly_scan",
            hour=settings.nightly_scan_cron_hour_utc,
            minute=settings.nightly_scan_cron_minute,
            second=0,
            microsecond=0,
            run_at_startup=False,
            unique=True,
        )
    ]


async def on_startup(ctx: dict[str, Any]) -> None:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    ctx["started_at"] = started_at
    logger.info(
        "ARQ worker started",
        extra={
            "queue_name": WORKER_QUEUE_NAME,
            "started_at": started_at.isoformat(),
        },
    )


async def on_shutdown(ctx: dict[str, Any]) -> None:
    started_at = ctx.get("started_at")
    started_at_iso = None
    if isinstance(started_at, datetime.datetime):
        started_at_iso = started_at.isoformat()

    logger.info(
        "ARQ worker stopped",
        extra={
            "queue_name": WORKER_QUEUE_NAME,
            "started_at": started_at_iso,
        },
    )


class WorkerSettings:
    functions = [
        audit_run_task,
        ingest_task,
        score_task,
        notification_task,
        nightly_scan,
    ]
    redis_settings = redis_settings_from_url(settings.redis_url)
    queue_name = WORKER_QUEUE_NAME
    timezone = datetime.timezone.utc
    cron_jobs = build_cron_jobs()
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
