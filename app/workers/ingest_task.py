import logging
import uuid
from typing import Any

from app.database import AsyncSessionLocal
from app.models.audit_job import AuditJob
from app.services.audit.audit_job_service import (
    increment_audit_job_progress,
    mark_audit_job_completed,
    mark_audit_job_failed,
    mark_audit_job_running,
)
from app.services.ingestion.source_sync_service import sync_source_by_id

logger = logging.getLogger(__name__)


async def ingest_task(
    _ctx: dict[str, Any],
    *,
    source_id: str,
    audit_job_id: str | None = None,
) -> dict[str, Any]:
    source_uuid: uuid.UUID | None = None
    audit_job_uuid: uuid.UUID | None = None

    try:
        source_uuid = uuid.UUID(source_id)
        audit_job_uuid = uuid.UUID(audit_job_id) if audit_job_id else None

        async with AsyncSessionLocal() as session:
            if audit_job_uuid is not None:
                existing_job = await session.get(AuditJob, audit_job_uuid)
                if existing_job is not None and existing_job.status == "completed":
                    payload = _completed_job_payload(
                        source_id=source_id,
                        audit_job_id=audit_job_id,
                        job=existing_job,
                    )
                    logger.info("ingest_task already completed", extra=payload)
                    return payload

                await mark_audit_job_running(session, audit_job_id=audit_job_uuid)

            result = await sync_source_by_id(source_uuid, db=session)

            if audit_job_uuid is not None:
                await increment_audit_job_progress(
                    session,
                    audit_job_id=audit_job_uuid,
                    docs_scanned_delta=result.documents_seen,
                )
                await mark_audit_job_completed(session, audit_job_id=audit_job_uuid)
    except Exception:
        logger.exception(
            "ingest_task failed",
            extra={"source_id": source_id, "audit_job_id": audit_job_id},
        )
        if audit_job_uuid is not None:
            await _mark_audit_job_failed_best_effort(
                audit_job_uuid,
                "ingest_task failed for source_id=<redacted>",
            )
        raise

    payload = {
        "status": "completed",
        "source_id": source_id,
        "audit_job_id": audit_job_id,
        "documents_seen": result.documents_seen,
        "documents_created": result.documents_created,
        "versions_created": result.versions_created,
    }
    logger.info("ingest_task completed", extra=payload)
    return payload


def _completed_job_payload(
    *, source_id: str, audit_job_id: str | None, job: AuditJob
) -> dict[str, Any]:
    return {
        "status": "completed",
        "source_id": source_id,
        "audit_job_id": audit_job_id,
        "documents_seen": job.docs_scanned or 0,
        "documents_created": 0,
        "versions_created": 0,
        "already_completed": True,
    }


async def _mark_audit_job_failed_best_effort(
    audit_job_id: uuid.UUID, error: str
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await mark_audit_job_failed(session, audit_job_id=audit_job_id, error=error)
    except Exception:
        logger.warning(
            "Failed to mark audit job as failed after ingest_task error",
            extra={"audit_job_id": str(audit_job_id)},
            exc_info=True,
        )
