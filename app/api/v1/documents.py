import uuid
import hashlib
from typing import List
from app.database import get_db
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.document import Document
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.document import DocumentResponse
from app.models.document_version import DocumentVersion
from fastapi import APIRouter, UploadFile, File, Depends, Query
from app.schemas.document import DocumentResponse, DocumentListResponse

router = APIRouter()


@router.post("/upload", status_code=201, response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()
    # check if this content already exists
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.content_hash == content_hash)
    )
    existing_version = result.scalar_one_or_none()
    if existing_version:
        # content unchanged - return existing document
        existing_doc = await db.get(Document, existing_version.document_id)
        return existing_doc
    # content is new - create document
    doc = Document(title=file.filename)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    version = DocumentVersion(
        document_id = doc.id,
        raw_content = content.decode("utf-8"),
        normalized_content = content.decode("utf-8"),
        content_hash = content_hash,
        version_number = 1
    )

    db.add(version)
    await db.commit()
    await db.refresh(version)

    # update doc to point to latest version
    doc.latest_version_id = version.id
    await db.commit()
    await db.refresh(doc)

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