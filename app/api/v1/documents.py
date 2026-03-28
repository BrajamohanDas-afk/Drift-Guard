import uuid
import hashlib
import datetime
from app.database import get_db
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.entity import Entity
from app.models.document import Document
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies.auth import require_api_key
from app.schemas.document import DocumentResponse
from app.models.document_version import DocumentVersion
from fastapi import APIRouter, UploadFile, File, Depends, Query
from app.services.extraction.entity_extractor import EntityExtractor
from app.services.ingestion.markdown_ingestor import MarkdownIngestor
from app.schemas.document import DocumentResponse, DocumentListResponse

router = APIRouter(dependencies=[Depends(require_api_key)])
ingestor = MarkdownIngestor()
extractor = EntityExtractor()
MAX_UPLOAD_BYTES = 1024 * 1024

async def find_existing_document(
    db: AsyncSession,
    *,
    title: str,
    source_id: uuid.UUID | None = None,
    path: str | None = None,
) -> Document | None:
    query = select(Document).where(Document.is_deleted == False)

    if source_id is None:
        query = query.where(
            Document.title == title,
            Document.source_id.is_(None),
        )
    else:
        if not path:
            raise ValueError("path is required for source-backed documents")
        query = query.where(
            Document.source_id == source_id,
            Document.path == path,
        )

    result = await db.execute(query.order_by(Document.created_at.desc()))
    return result.scalars().first()
    
@router.post("/upload", status_code=201, response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
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
    content_hash = hashlib.sha256(content).hexdigest()

    try:
    # direct uploads are source-less, so they are matched by filename only
        doc = await find_existing_document(
            db,
            title=file.filename,
            source_id=None,
            path=None,
        )

        if doc is None:
            doc = Document(
                title=file.filename,
                source_id=None,
                path=None,
            )
            db.add(doc)
            await db.flush()  # get doc.id without committing

        # check if content changed
        latest_version = None
        if doc.latest_version_id is not None:
            latest_version = await db.get(DocumentVersion, doc.latest_version_id)

        if latest_version and latest_version.content_hash == content_hash:
            return doc

        # create new version
        version = DocumentVersion(
            document_id=doc.id,
            raw_content=raw_text,
            normalized_content=ingestor.normalize(raw_text),
            content_hash=content_hash,
            version_number=1 if latest_version is None else latest_version.version_number + 1,
        )
        db.add(version)
        await db.flush()  # get version.id without committing

        # update latest version pointer
        doc.latest_version_id = version.id

        # extract and persist entities
        extraction_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        seen: set[tuple[str, str]] = set()

        for entity_data in extractor.extract(extraction_text):
            value = entity_data["value"].strip()
            key = (entity_data["entity_type"], value)
            if not value or key in seen:
                continue
            seen.add(key)
            db.add(Entity(
                document_id=doc.id,
                document_version_id=version.id,
                entity_type=entity_data["entity_type"],
                value=value,
                context=entity_data["context"],
            ))

        await db.commit()  # single commit — all or nothing
        await db.refresh(doc)
        return doc

    except Exception:
        await db.rollback()
        raise

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(default=1),
    per_page: int = Query(default=20),
    db: AsyncSession = Depends(get_db)
):
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.is_deleted == False)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Document)
        .where(Document.is_deleted == False)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    documents = result.scalars().all()

    return {
        "data": documents,
        "meta": {"total": total, "page": page, "per_page": per_page}
    }

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    doc = await db.get(Document, document_id)
    if not doc or doc.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.delete("/{document_id}", response_model=DocumentResponse)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    doc = await db.get(Document, document_id)
    if not doc :
        raise HTTPException(status_code=404, detail="Document not found")
    doc.is_deleted = True
    doc.deleted_at = datetime.datetime.now(datetime.timezone.utc)
    
    await db.commit()
    await db.refresh(doc)
    
    return doc
