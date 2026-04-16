import datetime
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_api_key
from app.models.document import Document
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.ingestion.document_ingestion_service import upsert_document

router = APIRouter(dependencies=[Depends(require_api_key)])
MAX_UPLOAD_BYTES = 1024 * 1024


@router.post("/upload", status_code=201, response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Uploaded file is too large",
        )
    try:
        raw_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be valid UTF-8 Markdown text",
        ) from exc

    try:
        result = await upsert_document(
            db,
            title=file.filename or "untitled.md",
            raw_text=raw_text,
            source_id=None,
            path=None,
        )
        await db.commit()
        await db.refresh(result.document)
        return result.document
    except Exception:
        await db.rollback()
        raise


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(
        select(func.count())
        .select_from(Document)
        .where(Document.is_deleted.is_(False))
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Document)
        .where(Document.is_deleted.is_(False))
        .order_by(Document.created_at.desc(), Document.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    documents = result.scalars().all()

    return {
        "data": documents,
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc or doc.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", response_model=DocumentResponse)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.is_deleted = True
    doc.deleted_at = datetime.datetime.now(datetime.timezone.utc)

    await db.commit()
    await db.refresh(doc)
    return doc
