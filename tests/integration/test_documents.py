import uuid
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.entity import Entity

TEST_HEADERS = {"x-api-key": settings.api_key}

async def test_upload_document_persists_version_normalized_content_and_entities():
    file_content = b"""# Payments Runbook

Owner: @platform
Service: payments-api
Dashboard: grafana:payments-main
Command: `kubectl get pods`
Env: PAYMENTS_API_URL
Role: arn:aws:iam::123456789012:role/payments-api
Chart: acme/payments-api@1.2.3
Cluster: prod-us-east-1-blue
URL: https://example.com/runbook.
"""

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/documents/upload",
            files={"file": ("payments.md", file_content, "text/markdown")},
            headers=TEST_HEADERS,
        )

    assert response.status_code == 201
    document_id = uuid.UUID(response.json()["id"])

    async with AsyncSessionLocal() as session:
        document = await session.get(Document, document_id)
        assert document is not None
        assert document.title == "payments.md"
        assert document.latest_version_id is not None

        version_result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.asc())
        )
        versions = version_result.scalars().all()

        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert versions[0].normalized_content == (
            "Payments Runbook Owner: @platform Service: payments-api "
            "Dashboard: grafana:payments-main Command: kubectl get pods "
            "Env: PAYMENTS_API_URL Role: arn:aws:iam::123456789012:role/payments-api "
            "Chart: acme/payments-api@1.2.3 Cluster: prod-us-east-1-blue "
            "URL: https://example.com/runbook."
        )

        entity_result = await session.execute(
            select(Entity.entity_type, Entity.value).where(
                Entity.document_version_id == versions[0].id
            )
        )
        entities = set(entity_result.all())

        expected_entities = {
            ("owner", "@platform"),
            ("service", "payments-api"),
            ("dashboard", "grafana:payments-main"),
            ("command", "kubectl get pods"),
            ("env_var", "PAYMENTS_API_URL"),
            ("iam_role", "arn:aws:iam::123456789012:role/payments-api"),
            ("helm_chart", "acme/payments-api@1.2.3"),
            ("cluster", "prod-us-east-1-blue"),
            ("url", "https://example.com/runbook"),
        }

        assert expected_entities <= entities


async def test_upload_same_content_is_a_noop_for_existing_document():
    file_content = b"# Test Runbook\n\nOwner: @platform\n"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first_response = await client.post(
            "/v1/documents/upload",
            files={"file": ("test.md", file_content, "text/markdown")},
            headers=TEST_HEADERS,
        )
        second_response = await client.post(
            "/v1/documents/upload",
            files={"file": ("test.md", file_content, "text/markdown")},
            headers=TEST_HEADERS,
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] == second_response.json()["id"]

    document_id = uuid.UUID(first_response.json()["id"])

    async with AsyncSessionLocal() as session:
        version_result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.asc())
        )
        versions = version_result.scalars().all()

        assert len(versions) == 1
        assert versions[0].version_number == 1


async def test_upload_changed_content_creates_new_version_for_same_document():
    first_content = b"# Test Runbook\n\nOwner: @platform\n"
    second_content = b"# Test Runbook\n\nOwner: @platform\nService: payments-api\n"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first_response = await client.post(
            "/v1/documents/upload",
            files={"file": ("test.md", first_content, "text/markdown")},
            headers=TEST_HEADERS,
        )
        second_response = await client.post(
            "/v1/documents/upload",
            files={"file": ("test.md", second_content, "text/markdown")},
            headers=TEST_HEADERS,
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] == second_response.json()["id"]

    document_id = uuid.UUID(first_response.json()["id"])

    async with AsyncSessionLocal() as session:
        document = await session.get(Document, document_id)
        assert document is not None
        assert document.latest_version_id is not None

        version_result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.asc())
        )
        versions = version_result.scalars().all()

        assert [version.version_number for version in versions] == [1, 2]
        assert versions[-1].id == document.latest_version_id


async def test_deleted_document_is_hidden_from_get_and_list():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        upload_response = await client.post(
            "/v1/documents/upload",
            files={"file": ("delete-me.md", b"# Delete Me", "text/markdown")},
            headers=TEST_HEADERS,
        )
        document_id = upload_response.json()["id"]

        delete_response = await client.delete(
            f"/v1/documents/{document_id}",
            headers=TEST_HEADERS,
        )
        get_response = await client.get(
            f"/v1/documents/{document_id}",
            headers=TEST_HEADERS,
        )
        list_response = await client.get(
            "/v1/documents",
            headers=TEST_HEADERS,
        )

    assert upload_response.status_code == 201
    assert delete_response.status_code == 200
    assert delete_response.json()["is_deleted"] is True
    assert get_response.status_code == 404
    assert all(item["id"] != document_id for item in list_response.json()["data"])

async def test_upload_rejects_invalid_utf8():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/documents/upload",
            files={"file": ("bad.md", b"\xff\xfe\xfa", "text/markdown")},
            headers=TEST_HEADERS,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be valid UTF-8 Markdown text"


async def test_upload_rejects_oversized_file():
    oversized_content = b"a" * ((1024 * 1024) + 2)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/documents/upload",
            files={"file": ("too-large.md", oversized_content, "text/markdown")},
            headers=TEST_HEADERS,
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded file is too large"