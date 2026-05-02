import uuid
from types import SimpleNamespace

import pytest

from app.models.source import Source
from app.services.ingestion.source_sync_service import (
    SourceNotFoundError,
    SourceSyncFetchError,
    SourceSyncProcessingError,
    SourceSyncValidationError,
    sync_source,
    sync_source_by_id,
    validate_source_can_sync,
)


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeSession:
    def __init__(self, source: Source | None = None):
        self._source = source
        self.get_calls = []
        self.commit_calls = 0
        self.rollback_calls = 0

    async def get(self, model, key):
        self.get_calls.append((model, key))
        return self._source

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


def _build_source(*, source_type: str = "git", config: dict | None = None) -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Runbooks",
        type=source_type,
        config=config or {"repo_url": "https://github.com/acme/runbooks"},
    )


def test_validate_source_can_sync_reuses_source_validation(
    monkeypatch: pytest.MonkeyPatch,
):
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    validate_source_can_sync(source)


def test_validate_source_can_sync_rejects_malformed_repo_url(
    monkeypatch: pytest.MonkeyPatch,
):
    source = _build_source(config={"repo_url": "https://gitlab.com/acme/runbooks"})
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    with pytest.raises(
        SourceSyncValidationError, match="repo_url must point to github.com"
    ):
        validate_source_can_sync(source)


@pytest.mark.asyncio
async def test_sync_source_by_id_not_found():
    session = _FakeSession(source=None)

    with pytest.raises(SourceNotFoundError, match="Source not found"):
        await sync_source_by_id(uuid.uuid4(), db=session)


@pytest.mark.asyncio
async def test_sync_source_requires_git_type():
    session = _FakeSession()
    source = _build_source(source_type="manual", config={})

    with pytest.raises(
        SourceSyncValidationError, match="Only git sources can be synced"
    ):
        await sync_source(source, db=session)


@pytest.mark.asyncio
async def test_sync_source_requires_repo_url():
    session = _FakeSession()
    source = _build_source(config={"branch": "main"})

    with pytest.raises(
        SourceSyncValidationError, match="Source config must include repo_url"
    ):
        await sync_source(source, db=session)


@pytest.mark.asyncio
async def test_sync_source_requires_github_token(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession()
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token", None
    )

    with pytest.raises(
        SourceSyncValidationError, match="GITHUB_TOKEN is not configured"
    ):
        await sync_source(source, db=session)


@pytest.mark.asyncio
async def test_sync_source_maps_fetch_errors(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession()
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    class _FakeIngestor:
        def fetch_markdown_files(self):
            raise RuntimeError("github outage")

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.GitIngestor",
        lambda **_kwargs: _FakeIngestor(),
    )

    with pytest.raises(SourceSyncFetchError, match="Failed to fetch repository files"):
        await sync_source(source, db=session)


@pytest.mark.asyncio
async def test_sync_source_maps_fetch_value_errors(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession()
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    class _FakeIngestor:
        def fetch_markdown_files(self):
            raise ValueError("invalid repo url")

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.GitIngestor",
        lambda **_kwargs: _FakeIngestor(),
    )

    with pytest.raises(SourceSyncValidationError, match="invalid repo url"):
        await sync_source(source, db=session)


@pytest.mark.asyncio
async def test_sync_source_maps_repo_access_to_validation_error(
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession()
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    class _RepoAccessError(RuntimeError):
        status = 404

    class _FakeIngestor:
        def fetch_markdown_files(self):
            raise _RepoAccessError("repo missing")

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.GitIngestor",
        lambda **_kwargs: _FakeIngestor(),
    )

    with pytest.raises(
        SourceSyncValidationError,
        match="Repository access failed; verify repo_url, branch, and token",
    ):
        await sync_source(source, db=session)


@pytest.mark.asyncio
async def test_sync_source_maps_wrapped_repo_access_to_validation_error(
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession()
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    class _RepoAccessError(RuntimeError):
        status = 403

    class _FakeIngestor:
        def fetch_markdown_files(self):
            raise RuntimeError("GitHub error: 403") from _RepoAccessError("private")

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.GitIngestor",
        lambda **_kwargs: _FakeIngestor(),
    )

    with pytest.raises(
        SourceSyncValidationError,
        match="Repository access failed; verify repo_url, branch, and token",
    ):
        await sync_source(source, db=session)


@pytest.mark.asyncio
async def test_sync_source_wraps_persist_failures(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession()
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    class _FakeIngestor:
        def fetch_markdown_files(self):
            return [{"filename": "a.md", "path": "docs/a.md", "content": "# A"}]

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.GitIngestor",
        lambda **_kwargs: _FakeIngestor(),
    )

    async def _failing_upsert(*_args, **_kwargs):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.upsert_document",
        _failing_upsert,
    )

    with pytest.raises(
        SourceSyncProcessingError, match="Failed to sync source documents"
    ):
        await sync_source(source, db=session)

    assert session.commit_calls == 0
    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_sync_source_persists_counts_and_commits(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession()
    source = _build_source()
    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.settings.github_token",
        "token",
    )

    files = [
        {"filename": "a.md", "path": "docs/a.md", "content": "# A"},
        {"filename": "b.md", "path": "docs/b.md", "content": "# B"},
    ]

    class _FakeIngestor:
        def fetch_markdown_files(self):
            return files

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.GitIngestor",
        lambda **_kwargs: _FakeIngestor(),
    )

    upsert_results = iter(
        [
            SimpleNamespace(created_document=True, created_version=True),
            SimpleNamespace(created_document=False, created_version=True),
        ]
    )
    upsert_calls: list[dict] = []

    async def fake_upsert_document(_db, **kwargs):
        upsert_calls.append(kwargs)
        return next(upsert_results)

    monkeypatch.setattr(
        "app.services.ingestion.source_sync_service.upsert_document",
        fake_upsert_document,
    )

    result = await sync_source(source, db=session)

    assert result.documents_seen == 2
    assert result.documents_created == 1
    assert result.versions_created == 2
    assert upsert_calls == [
        {
            "title": "a.md",
            "raw_text": "# A",
            "source_id": source.id,
            "path": "docs/a.md",
        },
        {
            "title": "b.md",
            "raw_text": "# B",
            "source_id": source.id,
            "path": "docs/b.md",
        },
    ]
    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert source.last_synced_at is not None
