import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.source import Source
from app.services.ingestion.document_ingestion_service import upsert_document
from app.services.ingestion.git_ingestor import GitIngestor


class SourceSyncError(RuntimeError):
    status_code = 400


class SourceNotFoundError(SourceSyncError):
    status_code = 404


class SourceSyncValidationError(SourceSyncError):
    status_code = 400


class SourceSyncFetchError(SourceSyncError):
    status_code = 502


class SourceSyncProcessingError(SourceSyncError):
    status_code = 500


@dataclass(frozen=True)
class SourceSyncResult:
    documents_seen: int
    documents_created: int
    versions_created: int


def _build_git_ingestor(source: Source) -> GitIngestor:
    if source.type != "git":
        raise SourceSyncValidationError("Only git sources can be synced")

    config = source.config or {}
    repo_url = config.get("repo_url")
    branch = config.get("branch", "main")
    path_filter = config.get("path_filter")

    if not repo_url:
        raise SourceSyncValidationError("Source config must include repo_url")
    if not settings.github_token:
        raise SourceSyncValidationError("GITHUB_TOKEN is not configured")

    return GitIngestor(
        repo_url=repo_url,
        token=settings.github_token,
        branch=branch,
        path_filter=path_filter,
    )


def _exception_status(exc: BaseException) -> int | None:
    current: BaseException | None = exc
    while current is not None:
        status = getattr(current, "status", None)
        if isinstance(status, int):
            return status
        current = current.__cause__ or current.__context__
    return None


def validate_source_can_sync(source: Source) -> None:
    try:
        _build_git_ingestor(source)._normalize_repo_name()
    except ValueError as exc:
        raise SourceSyncValidationError(str(exc)) from exc


async def sync_source(source: Source, *, db: AsyncSession) -> SourceSyncResult:
    git_ingestor = _build_git_ingestor(source)
    try:
        files = git_ingestor.fetch_markdown_files()
    except ValueError as exc:
        raise SourceSyncValidationError(str(exc)) from exc
    except Exception as exc:
        if _exception_status(exc) in {401, 403, 404, 422}:
            raise SourceSyncValidationError(
                "Repository access failed; verify repo_url, branch, and token"
            ) from exc
        raise SourceSyncFetchError("Failed to fetch repository files") from exc

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
    except SourceSyncError:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise SourceSyncProcessingError("Failed to sync source documents") from exc

    return SourceSyncResult(
        documents_seen=len(files),
        documents_created=created_documents,
        versions_created=created_versions,
    )


async def sync_source_by_id(
    source_id: uuid.UUID, *, db: AsyncSession
) -> SourceSyncResult:
    source = await db.get(Source, source_id)
    if source is None:
        raise SourceNotFoundError("Source not found")
    return await sync_source(source, db=db)
