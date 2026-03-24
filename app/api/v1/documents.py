import uuid
import hashlib
import datetime
from app.database import get_db
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.entity import Entity
from app.models.document import Document
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.document import DocumentResponse
from app.models.document_version import DocumentVersion
from fastapi import APIRouter, UploadFile, File, Depends, Query
from app.services.extraction.entity_extractor import EntityExtractor
from app.services.ingestion.markdown_ingestor import MarkdownIngestor
from app.schemas.document import DocumentResponse, DocumentListResponse

router = APIRouter()
ingestor = MarkdownIngestor()
extractor = EntityExtractor()
    
@router.post("/upload", status_code=201, response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    content = await file.read()
    raw_text = content.decode("utf-8")
    content_hash = hashlib.sha256(content).hexdigest()
    
    # check if this content already exists
    result = await db.execute(
        select(Document)
        .where(Document.title == file.filename, Document.is_deleted.is_(False))
        .order_by(Document.created_at.desc())
    )
    doc = result.scalars().first()

    if doc is None:
        doc = Document(title=file.filename)
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

    latest_version = None
    if doc.latest_version_id is not None:
        latest_version = await db.get(DocumentVersion, doc.latest_version_id)

    if latest_version and latest_version.content_hash == content_hash:
        return doc

    version = DocumentVersion(
        document_id=doc.id,
        raw_content=raw_text,
        normalized_content=ingestor.normalize(raw_text),
        content_hash=content_hash,
        version_number=1 if latest_version is None else latest_version.version_number + 1,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)

    doc.latest_version_id = version.id
    await db.commit()
    await db.refresh(doc)

    extraction_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    seen: set[tuple[str, str]] = set()

    for entity_data in extractor.extract(extraction_text):
        value = entity_data["value"].strip()
        key = (entity_data["entity_type"], value)

        if not value or key in seen:
            continue

        seen.add(key)
        entity = Entity(
            document_id=doc.id,
            document_version_id=version.id,
            entity_type=entity_data["entity_type"],
            value=value,
            context=entity_data["context"],
        )
        db.add(entity)

    await db.commit()
    return doc

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(default=1),
    per_page: int = Query(default=20),
    db: AsyncSession = Depends(get_db)
):
    # get total count
    count_result = await db.execute(select(func.count()).select_from(Document))
    total = count_result.scalar()

    # get paginated results
    result = await db.execute(
        select(Document).offset((page - 1) * per_page).limit(per_page)
    )
    documents = result.scalars().all()

    return {
        "data": documents,
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page
        }
    }

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    doc = await db.get(Document, document_id)
    if not doc :
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