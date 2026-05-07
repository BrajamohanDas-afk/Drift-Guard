import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.entity import Entity
from app.services.extraction.entity_extractor import EntityExtractor
from app.services.ingestion.markdown_ingestor import MarkdownIngestor

ingestor = MarkdownIngestor()
extractor = EntityExtractor()


def _stable_lock_id(*parts: str) -> int:
    raw = "||".join(parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()[:8]
    unsigned = int.from_bytes(digest, byteorder="big", signed=False)
    if unsigned >= 2**63:
        return unsigned - 2**64
    return unsigned


async def _acquire_document_lock(
    db: AsyncSession,
    *,
    title: str,
    source_id: uuid.UUID | None,
    path: str | None,
) -> None:
    if source_id is None:
        lock_id = _stable_lock_id("document_upsert", "standalone", path or title)
    else:
        if not path:
            raise ValueError("path is required for source-backed documents")
        lock_id = _stable_lock_id("document_upsert", str(source_id), path)
    await db.execute(select(func.pg_advisory_xact_lock(lock_id)))


async def _acquire_version_lock(db: AsyncSession, *, document_id: uuid.UUID) -> None:
    lock_id = _stable_lock_id("document_version", str(document_id))
    await db.execute(select(func.pg_advisory_xact_lock(lock_id)))


@dataclass
class DocumentIngestResult:
    document: Document
    created_document: bool
    created_version: bool


async def find_existing_document(
    db: AsyncSession,
    *,
    title: str,
    source_id: uuid.UUID | None,
    path: str | None,
) -> Document | None:
    query = select(Document).where(Document.is_deleted.is_(False))

    if source_id is None:
        query = query.where(Document.source_id.is_(None))
        if path is None:
            query = query.where(
                Document.title == title,
                Document.path.is_(None),
            )
        else:
            query = query.where(Document.path == path)
    else:
        if not path:
            raise ValueError("path is required for source-backed documents")
        query = query.where(
            Document.source_id == source_id,
            Document.path == path,
        )

    result = await db.execute(query.order_by(Document.created_at.desc()))
    return result.scalars().first()


async def upsert_document(
    db: AsyncSession,
    *,
    title: str,
    raw_text: str,
    source_id: uuid.UUID | None,
    path: str | None,
) -> DocumentIngestResult:
    await _acquire_document_lock(
        db,
        title=title,
        source_id=source_id,
        path=path,
    )

    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    doc = await find_existing_document(
        db,
        title=title,
        source_id=source_id,
        path=path,
    )

    created_document = False
    if doc is None:
        doc = Document(
            title=title,
            source_id=source_id,
            path=path,
        )
        db.add(doc)
        await db.flush()
        created_document = True
    else:
        doc.title = title
        doc.path = path
        if source_id is not None:
            doc.source_id = source_id

    await _acquire_version_lock(db, document_id=doc.id)

    latest_version = None
    if doc.latest_version_id is not None:
        latest_version = await db.get(DocumentVersion, doc.latest_version_id)

    if latest_version and latest_version.content_hash == content_hash:
        return DocumentIngestResult(
            document=doc,
            created_document=created_document,
            created_version=False,
        )

    version = DocumentVersion(
        document_id=doc.id,
        raw_content=raw_text,
        normalized_content=ingestor.normalize(raw_text),
        content_hash=content_hash,
        version_number=(
            1 if latest_version is None else latest_version.version_number + 1
        ),
    )
    db.add(version)
    await db.flush()

    doc.latest_version_id = version.id

    extraction_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    seen: set[tuple[str, str]] = set()

    for entity_data in extractor.extract(extraction_text):
        value = entity_data["value"].strip()
        key = (entity_data["entity_type"], value)
        if not value or key in seen:
            continue
        seen.add(key)
        db.add(
            Entity(
                document_id=doc.id,
                document_version_id=version.id,
                entity_type=entity_data["entity_type"],
                value=value,
                context=entity_data["context"],
            )
        )

    return DocumentIngestResult(
        document=doc,
        created_document=created_document,
        created_version=True,
    )
