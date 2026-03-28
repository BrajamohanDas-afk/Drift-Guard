import uuid
import datetime
from app.config import settings
from app.database import get_db
from sqlalchemy import func, select
from app.models.source import Source
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies.auth import require_api_key
from app.services.ingestion.git_ingestor import GitIngestor
from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.ingestion.document_ingestion_service import upsert_document
from app.schemas.source import SourceCreate, SourceListResponse, SourceResponse

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
    page: int = Query(default=1),
    per_page: int = Query(default=20),
    db: AsyncSession = Depends(get_db),
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
            "per_page": per_page,
        },
    }


@router.post("/{source_id}/sync", status_code=202)
async def sync_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.type != "git":
        raise HTTPException(status_code=400, detail="Only git sources can be synced")

    config = source.config or {}
    repo_url = config.get("repo_url")
    token = settings.github_token
    branch = config.get("branch", "main")
    path_filter = config.get("path_filter")

    if not repo_url:
        raise HTTPException(status_code=400, detail="Source config must include repo_url")
    if not token:
        raise HTTPException(status_code=400, detail="Source config must include token")

    git_ingestor = GitIngestor(
        repo_url=repo_url,
        token=token,
        branch=branch,
        path_filter=path_filter,
    )
    files = git_ingestor.fetch_markdown_files()

    created_documents = 0
    created_versions = 0

    try:
        for file_data in files:
            result = await upsert_document(
                db,
                title=file_data["filename"],
                raw_text=file_data["content"],
                source_id=source.id,
                path=file_data["path"],
            )
            created_documents += int(result.created_document)
            created_versions += int(result.created_version)

        source.last_synced_at = datetime.datetime.now(datetime.timezone.utc)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "data": {
            "audit_job_id": None,
            "documents_seen": len(files),
            "documents_created": created_documents,
            "versions_created": created_versions,
        }
    }
