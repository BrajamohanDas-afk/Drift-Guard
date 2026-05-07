import datetime
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_api_key
from app.dependencies.rate_limit import require_heavy_endpoint_rate_limit
from app.models.document import Document
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.ingestion.document_ingestion_service import upsert_document

router = APIRouter(dependencies=[Depends(require_api_key)])
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_DIRECT_UPLOAD_IDENTITY_LENGTH = 512
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
MARKDOWN_CONTENT_TYPES = {
    "application/octet-stream",
    "text/markdown",
    "text/plain",
    "text/x-markdown",
}


def _normalized_upload_filename(filename: str | None) -> str:
    normalized = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return normalized or "untitled.md"


def _has_markdown_extension(filename: str) -> bool:
    return any(
        filename.lower().endswith(extension)
        for extension in MARKDOWN_EXTENSIONS
    )


def _validate_markdown_upload(filename: str, content_type: str | None) -> None:
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if (
        not _has_markdown_extension(filename)
        and normalized_content_type not in MARKDOWN_CONTENT_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be Markdown",
        )


def _direct_upload_identity(filename: str, document_key: str | None) -> str:
    raw_identity = document_key if document_key is not None else filename
    identity = raw_identity.strip().replace("\\", "/").strip("/")

    if not identity:
        raise HTTPException(
            status_code=400,
            detail="document_key must not be blank",
        )
    if len(identity) > MAX_DIRECT_UPLOAD_IDENTITY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail="document_key is too long",
        )
    if "?" in identity or "#" in identity:
        raise HTTPException(
            status_code=400,
            detail="document_key must be a relative path-like identifier",
        )
    if any(part in {"", ".", ".."} for part in identity.split("/")):
        raise HTTPException(
            status_code=400,
            detail="document_key must be a relative path-like identifier",
        )

    return identity


@router.post(
    "/upload",
    status_code=201,
    response_model=DocumentResponse,
    dependencies=[Depends(require_heavy_endpoint_rate_limit)],
)
async def upload_document(
    file: UploadFile = File(...),
    document_key: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    filename = _normalized_upload_filename(file.filename)
    _validate_markdown_upload(filename, file.content_type)
    upload_identity = _direct_upload_identity(filename, document_key)

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
            title=filename,
            raw_text=raw_text,
            source_id=None,
            path=upload_identity,
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
