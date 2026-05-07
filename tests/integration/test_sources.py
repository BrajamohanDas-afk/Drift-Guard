import importlib
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit_job import AuditJob
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.source import Source
from app.services.ingestion.git_ingestor import GitIngestor
from app.services.ingestion.source_sync_service import sync_source_by_id
from app.workers.ingest_task import ingest_task
from app.workers.queue import QueueEnqueueError

sources_api_module = importlib.import_module("app.api.v1.sources")

TEST_HEADERS = {"x-api-key": settings.api_key}


async def test_sync_source_keeps_same_filename_documents_separate_by_path(
    monkeypatch,
):
    monkeypatch.setattr(settings, "github_token", "token")
    sync_payloads = [
        [
            {
                "filename": "runbook.md",
                "path": "docs/service-a/runbook.md",
                "content": "# Service A\n\nVersion 1",
            },
            {
                "filename": "runbook.md",
                "path": "docs/service-b/runbook.md",
                "content": "# Service B\n\nVersion 1",
            },
        ],
        [
            {
                "filename": "runbook.md",
                "path": "docs/service-a/runbook.md",
                "content": "# Service A\n\nVersion 2",
            },
            {
                "filename": "runbook.md",
                "path": "docs/service-b/runbook.md",
                "content": "# Service B\n\nVersion 1",
            },
        ],
    ]

    def fake_fetch_markdown_files(self):
        return sync_payloads.pop(0)

    monkeypatch.setattr(
        GitIngestor,
        "fetch_markdown_files",
        fake_fetch_markdown_files,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        create_source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Runbooks",
                "type": "git",
                "config": {
                    "repo_url": "https://github.com/acme/runbooks",
                    "branch": "main",
                    "path_filter": "docs/",
                },
            },
            headers=TEST_HEADERS,
        )
        assert create_source_response.status_code == 201
        source_uuid = uuid.UUID(create_source_response.json()["id"])

    async with AsyncSessionLocal() as session:
        await sync_source_by_id(source_uuid, db=session)
        await sync_source_by_id(source_uuid, db=session)

    async with AsyncSessionLocal() as session:
        document_result = await session.execute(
            select(Document)
            .where(Document.source_id == source_uuid)
            .order_by(Document.path.asc())
        )
        documents = document_result.scalars().all()

        assert len(documents) == 2
        assert [document.path for document in documents] == [
            "docs/service-a/runbook.md",
            "docs/service-b/runbook.md",
        ]
        assert all(document.title == "runbook.md" for document in documents)

        version_counts = {}
        for document in documents:
            version_result = await session.execute(
                select(DocumentVersion.version_number)
                .where(DocumentVersion.document_id == document.id)
                .order_by(DocumentVersion.version_number.asc())
            )
            version_counts[document.path] = version_result.scalars().all()

        assert version_counts == {
            "docs/service-a/runbook.md": [1, 2],
            "docs/service-b/runbook.md": [1],
        }


async def test_sync_source_endpoint_enqueues_background_job_and_returns_audit_job_id(
    monkeypatch,
):
    enqueue_calls = []
    monkeypatch.setattr(settings, "github_token", "token")

    async def fake_enqueue_ingest_task(*, source_id, audit_job_id, job_id):
        enqueue_calls.append((source_id, audit_job_id, job_id))
        return object()

    monkeypatch.setattr(
        sources_api_module,
        "enqueue_ingest_task",
        fake_enqueue_ingest_task,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        create_source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Queued Runbooks",
                "type": "git",
                "config": {"repo_url": "https://github.com/acme/runbooks"},
            },
            headers=TEST_HEADERS,
        )
        assert create_source_response.status_code == 201
        source_id = create_source_response.json()["id"]

        sync_response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )

    assert sync_response.status_code == 202
    payload = sync_response.json()["data"]
    audit_job_id = uuid.UUID(payload["audit_job_id"])
    assert payload == {
        "audit_job_id": str(audit_job_id),
        "status": "pending",
    }
    assert enqueue_calls == [
        (
            source_id,
            str(audit_job_id),
            f"source-sync:{source_id}:{audit_job_id}",
        )
    ]

    async with AsyncSessionLocal() as session:
        job = await session.get(AuditJob, audit_job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.triggered_by == f"source_sync:{source_id}"


async def test_sync_source_endpoint_payload_runs_through_worker_to_db(monkeypatch):
    enqueue_calls = []
    monkeypatch.setattr(settings, "github_token", "token")

    async def fake_enqueue_ingest_task(*, source_id, audit_job_id, job_id):
        enqueue_calls.append(
            {
                "source_id": source_id,
                "audit_job_id": audit_job_id,
                "job_id": job_id,
            }
        )
        return object()

    def fake_fetch_markdown_files(self):
        return [
            {
                "filename": "worker-runbook.md",
                "path": "docs/worker-runbook.md",
                "content": "# Worker Runbook\n\nOwner: @platform",
            }
        ]

    monkeypatch.setattr(
        sources_api_module,
        "enqueue_ingest_task",
        fake_enqueue_ingest_task,
    )
    monkeypatch.setattr(
        GitIngestor,
        "fetch_markdown_files",
        fake_fetch_markdown_files,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        create_source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Worker Runbooks",
                "type": "git",
                "config": {"repo_url": "https://github.com/acme/runbooks"},
            },
            headers=TEST_HEADERS,
        )
        assert create_source_response.status_code == 201
        source_id = create_source_response.json()["id"]

        sync_response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )

    assert sync_response.status_code == 202
    assert len(enqueue_calls) == 1

    worker_result = await ingest_task(
        {},
        source_id=enqueue_calls[0]["source_id"],
        audit_job_id=enqueue_calls[0]["audit_job_id"],
    )

    assert worker_result == {
        "status": "completed",
        "source_id": source_id,
        "audit_job_id": enqueue_calls[0]["audit_job_id"],
        "documents_seen": 1,
        "documents_created": 1,
        "versions_created": 1,
    }

    async with AsyncSessionLocal() as session:
        audit_job = await session.get(
            AuditJob,
            uuid.UUID(enqueue_calls[0]["audit_job_id"]),
        )
        assert audit_job is not None
        assert audit_job.status == "completed"
        assert audit_job.docs_scanned == 1

        document_result = await session.execute(select(Document))
        document = document_result.scalars().one()
        assert document.source_id == uuid.UUID(source_id)
        assert document.path == "docs/worker-runbook.md"
        assert document.latest_version_id is not None


async def test_sync_source_endpoint_marks_job_failed_when_enqueue_fails(
    monkeypatch,
):
    monkeypatch.setattr(settings, "github_token", "token")

    async def fake_enqueue_ingest_task(**_kwargs):
        raise QueueEnqueueError("queue unavailable")

    monkeypatch.setattr(
        sources_api_module,
        "enqueue_ingest_task",
        fake_enqueue_ingest_task,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        create_source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Queue Failure",
                "type": "git",
                "config": {"repo_url": "https://github.com/acme/runbooks"},
            },
            headers=TEST_HEADERS,
        )
        assert create_source_response.status_code == 201
        source_id = create_source_response.json()["id"]

        sync_response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )

    assert sync_response.status_code == 503
    assert sync_response.json()["detail"] == "Failed to enqueue source sync"

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AuditJob))
        job = result.scalars().one()
        assert job.status == "failed"
        assert job.error == "Failed to enqueue source sync"
        assert job.triggered_by == f"source_sync:{source_id}"


async def test_sources_endpoints_require_api_key():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        list_response = await client.get("/v1/sources")
        create_response = await client.post(
            "/v1/sources",
            json={
                "name": "NoAuth",
                "type": "git",
                "config": {"repo_url": "https://github.com/acme/runbooks"},
            },
        )
        sync_response = await client.post(f"/v1/sources/{uuid.uuid4()}/sync")

    assert list_response.status_code == 401
    assert create_response.status_code == 401
    assert sync_response.status_code == 401


async def test_sources_list_validates_pagination_bounds():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        invalid_page = await client.get(
            "/v1/sources",
            params={"page": 0},
            headers=TEST_HEADERS,
        )
        invalid_page_size = await client.get(
            "/v1/sources",
            params={"per_page": 101},
            headers=TEST_HEADERS,
        )

    assert invalid_page.status_code == 422
    assert invalid_page_size.status_code == 422


async def test_sync_source_returns_not_found_for_unknown_source():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/v1/sources/{uuid.uuid4()}/sync",
            headers=TEST_HEADERS,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found"


async def test_sync_source_rejects_non_git_sources():
    async with AsyncSessionLocal() as session:
        source = Source(name="Manual", type="manual", config={})
        session.add(source)
        await session.commit()
        await session.refresh(source)
        source_id = source.id

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only git sources can be synced"


async def test_sync_source_requires_repo_url_in_config():
    async with AsyncSessionLocal() as session:
        source = Source(name="BrokenGit", type="git", config={"branch": "main"})
        session.add(source)
        await session.commit()
        await session.refresh(source)
        source_id = source.id

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Source config must include repo_url"


async def test_sync_source_requires_github_token(monkeypatch):
    async with AsyncSessionLocal() as session:
        source = Source(
            name="TokenlessGit",
            type="git",
            config={"repo_url": "https://github.com/acme/runbooks"},
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        source_id = source.id

    monkeypatch.setattr(settings, "github_token", None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "GITHUB_TOKEN is not configured"
