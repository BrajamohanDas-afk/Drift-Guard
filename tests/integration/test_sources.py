from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.services.ingestion.git_ingestor import GitIngestor

TEST_HEADERS = {"x-api-key": settings.api_key}

async def test_sync_source_keeps_same_filename_documents_separate_by_path(
    monkeypatch,
):
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
        source_id = create_source_response.json()["id"]

        first_sync_response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )
        assert first_sync_response.status_code == 202

        second_sync_response = await client.post(
            f"/v1/sources/{source_id}/sync",
            headers=TEST_HEADERS,
        )
        assert second_sync_response.status_code == 202

    async with AsyncSessionLocal() as session:
        document_result = await session.execute(
            select(Document)
            .where(Document.source_id == source_id)
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
