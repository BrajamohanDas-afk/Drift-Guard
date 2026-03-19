import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.source import Source
from app.schemas.source import SourceCreate, SourceResponse, SourceListResponse

router = APIRouter()

@router.post("", status_code=201, response_model=SourceResponse)
async def create_source(
    source_data: SourceCreate,
    db: AsyncSession = Depends(get_db)
):
    source = Source(
        name=source_data.name,
        type=source_data.type,
        config=source_data.config
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source

@router.get("", response_model=SourceListResponse)
async def list_sources(
    page: int = Query(default=1),
    per_page: int = Query(default=20),
    db: AsyncSession = Depends(get_db)
):
    count_result = await db.execute(select(func.count()).select_from(Source))
    total = count_result.scalar()

    result = await db.execute(
        select(Source).offset((page - 1) * per_page).limit(per_page)
    )
    sources = result.scalars().all()

    return {
        "data": sources,
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page
        }
    }

@router.post("/{source_id}/sync", status_code=202)
async def sync_source(source_id: uuid.UUID):
    return {"data": {"audit_job_id": None, "message": "Sync scheduled — background jobs coming in Phase 7"}}