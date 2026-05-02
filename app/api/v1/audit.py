import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_api_key
from app.models.audit_job import AuditJob
from app.schemas.audit_job import (
    AuditJobListResponse,
    AuditJobResponse,
    AuditJobStatus,
    AuditRunRequest,
)
from app.schemas.audit_report import AuditReportResponse
from app.services.audit.audit_job_service import (
    AuditJobNotFoundError,
    create_audit_job,
    get_audit_job,
    mark_audit_job_failed,
)
from app.services.audit.audit_report_service import (
    AuditReportService,
    AuditReportValidationError,
    AuditServiceNotFoundError,
)
from app.workers.queue import QueueEnqueueError, enqueue_audit_run_task

router = APIRouter(dependencies=[Depends(require_api_key)])
audit_report_service = AuditReportService()


@router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AuditJobResponse,
)
async def run_audit(
    request: AuditRunRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    triggered_by = request.triggered_by if request is not None else "manual"
    job = await create_audit_job(db, triggered_by=triggered_by)

    try:
        await enqueue_audit_run_task(
            audit_job_id=str(job.id),
            job_id=f"audit-run:{job.id}",
        )
    except QueueEnqueueError as exc:
        await mark_audit_job_failed(
            db,
            audit_job_id=job.id,
            error="Failed to enqueue audit run",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue audit run",
        ) from exc

    return job


@router.get("/jobs", response_model=AuditJobListResponse)
async def list_audit_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status_filter: AuditJobStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    count_query = select(func.count()).select_from(AuditJob)
    list_query = select(AuditJob)

    if status_filter is not None:
        count_query = count_query.where(AuditJob.status == status_filter)
        list_query = list_query.where(AuditJob.status == status_filter)

    count_result = await db.execute(count_query)
    total = int(count_result.scalar() or 0)

    result = await db.execute(
        list_query.order_by(
            AuditJob.started_at.desc().nullsfirst(),
            AuditJob.id.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    jobs = result.scalars().all()

    return {
        "data": jobs,
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.get("/jobs/{audit_job_id}", response_model=AuditJobResponse)
async def get_audit_job_detail(
    audit_job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_audit_job(db, audit_job_id=audit_job_id)
    except AuditJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Audit job not found") from exc


@router.get("/report", response_model=AuditReportResponse)
async def get_audit_report(
    db: AsyncSession = Depends(get_db),
):
    return await audit_report_service.get_global_report(db)


@router.get("/service/{service_name}", response_model=AuditReportResponse)
async def get_service_audit_report(
    service_name: str = Path(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await audit_report_service.get_service_report(
            db,
            service_name=service_name,
        )
    except AuditReportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AuditServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Service not found") from exc
