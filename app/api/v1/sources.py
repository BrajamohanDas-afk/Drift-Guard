import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_api_key
from app.dependencies.rate_limit import require_heavy_endpoint_rate_limit
from app.models.source import Source
from app.schemas.source import (
    SourceCreate,
    SourceListResponse,
    SourceResponse,
    SourceSyncResponse,
)
from app.services.audit.audit_job_service import (
    create_audit_job,
    mark_audit_job_failed,
)
from app.services.ingestion.source_sync_service import (
    SourceSyncError,
    validate_source_can_sync,
)
from app.workers.queue import QueueEnqueueError, enqueue_ingest_task

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("", status_code=201, response_model=SourceResponse)
async def create_source(
    source_data: SourceCreate,
    db: AsyncSession = Depends(get_db),
):
    source = Source(
        name=source_data.name,
        type=source_data.type,
        config=source_data.config.model_dump(exclude_none=True),
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("", response_model=SourceListResponse)
async def list_sources(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(select(func.count()).select_from(Source))
    total = count_result.scalar()

    result = await db.execute(
        select(Source)
        .order_by(Source.created_at.desc(), Source.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    sources = result.scalars().all()

    return {
        "data": sources,
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page,
        },
    }


@router.post(
    "/{source_id}/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SourceSyncResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_heavy_endpoint_rate_limit)],
)
async def sync_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        validate_source_can_sync(source)
    except SourceSyncError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    audit_job = await create_audit_job(db, triggered_by=f"source_sync:{source_id}")

    try:
        queued_job = await enqueue_ingest_task(
            source_id=str(source_id),
            audit_job_id=str(audit_job.id),
            job_id=f"source-sync:{source_id}:{audit_job.id}",
        )
        if queued_job is None:
            raise QueueEnqueueError("source sync job was not enqueued")
    except QueueEnqueueError as exc:
        await mark_audit_job_failed(
            db,
            audit_job_id=audit_job.id,
            error="Failed to enqueue source sync",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue source sync",
        ) from exc

    return {
        "data": {
            "audit_job_id": audit_job.id,
            "status": audit_job.status,
        }
    }
