import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.audit_job import AuditJob
from app.models.source import Source
from app.services.audit.audit_job_service import (
    increment_audit_job_progress,
    mark_audit_job_completed,
    mark_audit_job_failed,
    mark_audit_job_running,
)
from app.services.audit.audit_scan_service import scan_all_documents
from app.services.ingestion.source_sync_service import sync_source_by_id

logger = logging.getLogger(__name__)


async def _list_source_ids(db: AsyncSession) -> list[uuid.UUID]:
    result = await db.execute(
        select(Source.id).order_by(Source.created_at.asc(), Source.id.asc())
    )
    return list(result.scalars().all())


async def audit_run_task(
    _ctx: dict[str, Any],
    *,
    audit_job_id: str,
) -> dict[str, Any]:
    audit_job_uuid = uuid.UUID(audit_job_id)
    source_ids: list[uuid.UUID] = []
    documents_seen = 0
    documents_created = 0
    versions_created = 0
    alerts_created = 0
    alerts_resolved = 0
    scores_refreshed = 0

    try:
        async with AsyncSessionLocal() as session:
            existing_job = await session.get(AuditJob, audit_job_uuid)
            if existing_job is not None and existing_job.status == "completed":
                payload = _completed_job_payload(audit_job_id, existing_job)
                logger.info("audit_run_task already completed", extra=payload)
                return payload

            await mark_audit_job_running(session, audit_job_id=audit_job_uuid)
            source_ids = await _list_source_ids(session)

            for source_id in source_ids:
                sync_result = await sync_source_by_id(source_id, db=session)
                documents_seen += sync_result.documents_seen
                documents_created += sync_result.documents_created
                versions_created += sync_result.versions_created

            scan_result = await scan_all_documents(session)
            documents_seen = scan_result.documents_scanned
            alerts_created = scan_result.alerts_created
            alerts_resolved = scan_result.alerts_resolved
            scores_refreshed = scan_result.scores_refreshed
            await increment_audit_job_progress(
                session,
                audit_job_id=audit_job_uuid,
                docs_scanned_delta=scan_result.documents_scanned,
                alerts_created_delta=scan_result.alerts_created,
            )

            await mark_audit_job_completed(session, audit_job_id=audit_job_uuid)
    except Exception:
        logger.exception(
            "audit_run_task failed",
            extra={"audit_job_id": audit_job_id},
        )
        await _mark_audit_job_failed_best_effort(
            audit_job_uuid,
            "audit_run_task failed",
        )
        raise

    payload = {
        "status": "completed",
        "audit_job_id": audit_job_id,
        "sources_seen": len(source_ids),
        "documents_seen": documents_seen,
        "documents_created": documents_created,
        "versions_created": versions_created,
        "alerts_created": alerts_created,
        "alerts_resolved": alerts_resolved,
        "scores_refreshed": scores_refreshed,
    }
    logger.info("audit_run_task completed", extra=payload)
    return payload


def _completed_job_payload(audit_job_id: str, job: AuditJob) -> dict[str, Any]:
    return {
        "status": "completed",
        "audit_job_id": audit_job_id,
        "sources_seen": 0,
        "documents_seen": job.docs_scanned or 0,
        "documents_created": 0,
        "versions_created": 0,
        "alerts_created": job.alerts_created or 0,
        "alerts_resolved": 0,
        "scores_refreshed": 0,
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
            "Failed to mark audit job as failed after audit_run_task error",
            extra={"audit_job_id": str(audit_job_id)},
            exc_info=True,
        )
