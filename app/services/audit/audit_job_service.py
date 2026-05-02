import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_job import AuditJob


class AuditJobError(RuntimeError):
    pass


class AuditJobNotFoundError(AuditJobError):
    pass


class AuditJobStateError(AuditJobError):
    pass


class AuditJobValidationError(AuditJobError):
    pass


IMMUTABLE_AUDIT_STATES = {"completed"}


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def create_audit_job(
    db: AsyncSession, *, triggered_by: str | None = None
) -> AuditJob:
    job = AuditJob(
        id=uuid.uuid4(),
        triggered_by=triggered_by,
        status="pending",
        docs_scanned=0,
        alerts_created=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_audit_job(db: AsyncSession, *, audit_job_id: uuid.UUID) -> AuditJob:
    job = await db.get(AuditJob, audit_job_id)
    if job is None:
        raise AuditJobNotFoundError("Audit job not found")
    return job


async def _get_audit_job_for_update(
    db: AsyncSession, *, audit_job_id: uuid.UUID
) -> AuditJob:
    if hasattr(db, "execute"):
        result = await db.execute(
            select(AuditJob).where(AuditJob.id == audit_job_id).with_for_update()
        )
        job = result.scalars().first()
        if job is not None:
            return job
    return await get_audit_job(db, audit_job_id=audit_job_id)


async def mark_audit_job_running(
    db: AsyncSession, *, audit_job_id: uuid.UUID
) -> AuditJob:
    job = await _get_audit_job_for_update(db, audit_job_id=audit_job_id)
    if job.status in IMMUTABLE_AUDIT_STATES:
        raise AuditJobStateError(f"Cannot move terminal audit job to running: {job.id}")

    if job.started_at is None:
        job.started_at = _utcnow()
    if job.docs_scanned is None:
        job.docs_scanned = 0
    if job.alerts_created is None:
        job.alerts_created = 0
    if job.status == "failed":
        job.completed_at = None
        job.error = None
    job.status = "running"

    await db.commit()
    await db.refresh(job)
    return job


async def increment_audit_job_progress(
    db: AsyncSession,
    *,
    audit_job_id: uuid.UUID,
    docs_scanned_delta: int = 0,
    alerts_created_delta: int = 0,
) -> AuditJob:
    if docs_scanned_delta < 0:
        raise AuditJobValidationError("docs_scanned_delta must be >= 0")
    if alerts_created_delta < 0:
        raise AuditJobValidationError("alerts_created_delta must be >= 0")

    job = await _get_audit_job_for_update(db, audit_job_id=audit_job_id)
    if job.status in IMMUTABLE_AUDIT_STATES:
        raise AuditJobStateError(
            f"Cannot update progress for terminal audit job: {job.id}"
        )

    if job.started_at is None:
        job.started_at = _utcnow()
    if job.docs_scanned is None:
        job.docs_scanned = 0
    if job.alerts_created is None:
        job.alerts_created = 0

    job.status = "running"
    if job.completed_at is not None:
        job.completed_at = None
    if job.error is not None:
        job.error = None
    job.docs_scanned += docs_scanned_delta
    job.alerts_created += alerts_created_delta

    await db.commit()
    await db.refresh(job)
    return job


async def mark_audit_job_completed(
    db: AsyncSession, *, audit_job_id: uuid.UUID
) -> AuditJob:
    job = await _get_audit_job_for_update(db, audit_job_id=audit_job_id)
    if job.status == "completed":
        return job
    if job.status == "failed":
        raise AuditJobStateError(f"Cannot complete failed audit job: {job.id}")

    now = _utcnow()
    if job.started_at is None:
        job.started_at = now
    job.status = "completed"
    job.completed_at = now
    job.error = None

    await db.commit()
    await db.refresh(job)
    return job


async def mark_audit_job_failed(
    db: AsyncSession, *, audit_job_id: uuid.UUID, error: str
) -> AuditJob:
    job = await _get_audit_job_for_update(db, audit_job_id=audit_job_id)
    if job.status == "failed":
        return job
    if job.status == "completed":
        raise AuditJobStateError(f"Cannot fail completed audit job: {job.id}")

    now = _utcnow()
    if job.started_at is None:
        job.started_at = now
    job.status = "failed"
    job.completed_at = now
    job.error = error

    await db.commit()
    await db.refresh(job)
    return job
