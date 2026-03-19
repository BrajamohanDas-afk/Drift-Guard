import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_upload_document():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        file_content = b"# Test Runbook\n\nThis is a test."
        response = await client.post(
            "/v1/documents/upload",
            files={"file": ("test.md", file_content, "text/markdown")}
        )
        assert response.status_code == 201

async def test_get_document():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        file_content = b"# Test Runbook get\n\nThis is a get test."
        upload = await client.post(
            "/v1/documents/upload",
            files={"file": ("test-get.md", file_content, "text/markdown")}
        )
        document_id = upload.json()["id"]
        response = await client.get(f"/v1/documents/{document_id}")
        assert response.status_code == 200

async def test_delete_document():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        file_content = b"# Delete Test Runbook\n\nThis is a delete test."
        upload = await client.post(
            "/v1/documents/upload",
            files={"file": ("test-delete.md", file_content, "text/markdown")}
        )
        document_id = upload.json()["id"]
        response = await client.delete(f"/v1/documents/{document_id}")
        assert response.status_code == 200
        assert response.json()["is_deleted"] == True

async def test_list_documents():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/documents")
        assert response.status_code == 200
        assert "data" in response.json()
        assert "meta" in response.json()