import importlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

documents_api = importlib.import_module("app.api.v1.documents")


class _FakeUploadFile:
    def __init__(
        self,
        *,
        filename: str,
        content: bytes = b"# Runbook",
        content_type: str = "text/markdown",
    ):
        self.filename = filename
        self.content = content
        self.content_type = content_type

    async def read(self, _size: int) -> bytes:
        return self.content


class _FakeDb:
    def __init__(self):
        self.committed = False
        self.refreshed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def refresh(self, _document):
        self.refreshed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_upload_document_uses_document_key_as_direct_identity(monkeypatch):
    calls = []

    async def fake_upsert_document(_db, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            document=SimpleNamespace(
                id=uuid.uuid4(),
                title=kwargs["title"],
                path=kwargs["path"],
            )
        )

    monkeypatch.setattr(documents_api, "upsert_document", fake_upsert_document)
    db = _FakeDb()

    document = await documents_api.upload_document(
        file=_FakeUploadFile(filename="runbook.md"),
        document_key="team-a/runbook.md",
        db=db,
    )

    assert document.title == "runbook.md"
    assert document.path == "team-a/runbook.md"
    assert calls == [
        {
            "title": "runbook.md",
            "raw_text": "# Runbook",
            "source_id": None,
            "path": "team-a/runbook.md",
        }
    ]
    assert db.committed is True
    assert db.refreshed is True


@pytest.mark.asyncio
async def test_upload_document_defaults_direct_identity_to_filename(monkeypatch):
    calls = []

    async def fake_upsert_document(_db, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(document=SimpleNamespace(id=uuid.uuid4()))

    monkeypatch.setattr(documents_api, "upsert_document", fake_upsert_document)

    await documents_api.upload_document(
        file=_FakeUploadFile(filename="C:\\tmp\\runbook.md"),
        document_key=None,
        db=_FakeDb(),
    )

    assert calls[0]["title"] == "runbook.md"
    assert calls[0]["path"] == "runbook.md"


@pytest.mark.asyncio
async def test_upload_document_rejects_non_markdown_file():
    with pytest.raises(HTTPException) as exc_info:
        await documents_api.upload_document(
            file=_FakeUploadFile(
                filename="runbook.pdf",
                content=b"%PDF",
                content_type="application/pdf",
            ),
            document_key=None,
            db=_FakeDb(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Uploaded file must be Markdown"


@pytest.mark.asyncio
async def test_upload_document_rejects_unsafe_document_key():
    with pytest.raises(HTTPException) as exc_info:
        await documents_api.upload_document(
            file=_FakeUploadFile(filename="runbook.md"),
            document_key="../runbook.md",
            db=_FakeDb(),
        )

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "document_key must be a relative path-like identifier"
    )
