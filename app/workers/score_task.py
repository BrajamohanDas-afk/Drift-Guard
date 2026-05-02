import logging
import uuid
from typing import Any

from app.database import AsyncSessionLocal
from app.services.audit.audit_job_service import (
    mark_audit_job_failed,
    mark_audit_job_running,
)
from app.services.scoring.scoring_service import ScoringService

logger = logging.getLogger(__name__)
scoring_service = ScoringService()


async def score_task(
    _ctx: dict[str, Any],
    *,
    document_id: str,
    audit_job_id: str | None = None,
) -> dict[str, Any]:
    document_uuid: uuid.UUID | None = None
    audit_job_uuid: uuid.UUID | None = None

    try:
        document_uuid = uuid.UUID(document_id)
        audit_job_uuid = uuid.UUID(audit_job_id) if audit_job_id else None

        async with AsyncSessionLocal() as session:
            if audit_job_uuid is not None:
                await mark_audit_job_running(session, audit_job_id=audit_job_uuid)
            snapshot = await scoring_service.score_document(
                session, document_id=document_uuid
            )
    except Exception:
        logger.exception(
            "score_task failed",
            extra={
                "document_id": document_id,
                "audit_job_id": audit_job_id,
            },
        )
        if audit_job_uuid is not None:
            await _mark_audit_job_failed_best_effort(
                audit_job_uuid,
                "score_task failed for document_id=<redacted>",
            )
        raise

    payload = {
        "status": "completed",
        "document_id": document_id,
        "audit_job_id": audit_job_id,
        "score_id": str(snapshot.id),
        "score": float(snapshot.score),
        "scored_at": snapshot.scored_at.isoformat(),
    }
    logger.info("score_task completed", extra=payload)
    return payload


async def _mark_audit_job_failed_best_effort(
    audit_job_id: uuid.UUID, error: str
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await mark_audit_job_failed(session, audit_job_id=audit_job_id, error=error)
    except Exception:
        logger.warning(
            "Failed to mark audit job as failed after score_task error",
            extra={"audit_job_id": str(audit_job_id)},
            exc_info=True,
        )
