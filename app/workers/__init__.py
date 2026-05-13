from typing import Any

from app.workers.audit_run_task import audit_run_task
from app.workers.common import WORKER_QUEUE_NAME
from app.workers.ingest_task import ingest_task
from app.workers.nightly_scan import nightly_scan
from app.workers.notification_task import notification_task
from app.workers.queue import (
    QueueCapacityError,
    QueueEnqueueError,
    enqueue_audit_run_task,
    enqueue_ingest_task,
    enqueue_nightly_scan,
    enqueue_notification_task,
    enqueue_score_task,
)
from app.workers.score_task import score_task

__all__ = [
    "QueueEnqueueError",
    "QueueCapacityError",
    "WORKER_QUEUE_NAME",
    "WorkerSettings",
    "audit_run_task",
    "enqueue_audit_run_task",
    "enqueue_ingest_task",
    "enqueue_nightly_scan",
    "enqueue_notification_task",
    "enqueue_score_task",
    "ingest_task",
    "nightly_scan",
    "notification_task",
    "score_task",
]


def __getattr__(name: str) -> Any:
    if name == "WorkerSettings":
        # Lazy import avoids loading runtime settings for queue-only imports.
        from app.workers.runtime import WorkerSettings

        return WorkerSettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
