import importlib
import uuid
from types import SimpleNamespace

import pytest

ingest_task_module = importlib.import_module("app.workers.ingest_task")


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeSessionContext:
    def __init__(self, session_obj):
        self._session_obj = session_obj

    async def __aenter__(self):
        return self._session_obj

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    async def get(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_ingest_task_syncs_source_and_updates_audit_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = _FakeSession()
    captured = {}
    transitions: list[tuple[str, uuid.UUID, int | None]] = []

    async def fake_sync_source_by_id(source_uuid, *, db):
        captured["source_uuid"] = source_uuid
        captured["db"] = db
        return SimpleNamespace(
            documents_seen=3,
            documents_created=2,
            versions_created=2,
        )

    async def fake_mark_audit_job_running(db, *, audit_job_id):
        assert db is fake_session
        transitions.append(("running", audit_job_id, None))

    async def fake_increment_audit_job_progress(
        db, *, audit_job_id, docs_scanned_delta=0, alerts_created_delta=0
    ):
        assert db is fake_session
        assert alerts_created_delta == 0
        transitions.append(("progress", audit_job_id, docs_scanned_delta))

    async def fake_mark_audit_job_completed(db, *, audit_job_id):
        assert db is fake_session
        transitions.append(("completed", audit_job_id, None))

    monkeypatch.setattr(
        ingest_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        ingest_task_module,
        "sync_source_by_id",
        fake_sync_source_by_id,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "mark_audit_job_running",
        fake_mark_audit_job_running,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "increment_audit_job_progress",
        fake_increment_audit_job_progress,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "mark_audit_job_completed",
        fake_mark_audit_job_completed,
    )

    source_id = str(uuid.uuid4())
    audit_job_id = str(uuid.uuid4())
    result = await ingest_task_module.ingest_task(
        {},
        source_id=source_id,
        audit_job_id=audit_job_id,
    )

    assert captured["source_uuid"] == uuid.UUID(source_id)
    assert captured["db"] is fake_session
    assert transitions == [
        ("running", uuid.UUID(audit_job_id), None),
        ("progress", uuid.UUID(audit_job_id), 3),
        ("completed", uuid.UUID(audit_job_id), None),
    ]
    assert result == {
        "status": "completed",
        "source_id": source_id,
        "audit_job_id": audit_job_id,
        "documents_seen": 3,
        "documents_created": 2,
        "versions_created": 2,
    }


@pytest.mark.asyncio
async def test_ingest_task_marks_audit_failed_on_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = _FakeSession()
    failure_calls = []
    events = []

    async def fake_sync_source_by_id(*_args, **_kwargs):
        events.append("sync")
        raise RuntimeError("sync failure")

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        events.append("running")
        return None

    async def fake_mark_failed_best_effort(audit_job_id, error):
        failure_calls.append((audit_job_id, error))

    monkeypatch.setattr(
        ingest_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        ingest_task_module,
        "sync_source_by_id",
        fake_sync_source_by_id,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "mark_audit_job_running",
        fake_mark_audit_job_running,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "_mark_audit_job_failed_best_effort",
        fake_mark_failed_best_effort,
    )

    audit_job_uuid = uuid.uuid4()
    with pytest.raises(RuntimeError, match="sync failure"):
        await ingest_task_module.ingest_task(
            {},
            source_id=str(uuid.uuid4()),
            audit_job_id=str(audit_job_uuid),
        )

    assert events == ["running", "sync"]
    assert failure_calls == [
        (audit_job_uuid, "ingest_task failed for source_id=<redacted>")
    ]


@pytest.mark.asyncio
async def test_ingest_task_rejects_invalid_source_id(
    monkeypatch: pytest.MonkeyPatch,
):
    called = False

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        ingest_task_module, "mark_audit_job_running", fake_mark_audit_job_running
    )

    with pytest.raises(ValueError):
        await ingest_task_module.ingest_task({}, source_id="not-a-uuid")

    assert called is False


@pytest.mark.asyncio
async def test_ingest_task_rejects_invalid_audit_job_id(
    monkeypatch: pytest.MonkeyPatch,
):
    called = False

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        ingest_task_module, "mark_audit_job_running", fake_mark_audit_job_running
    )

    with pytest.raises(ValueError):
        await ingest_task_module.ingest_task(
            {},
            source_id=str(uuid.uuid4()),
            audit_job_id="not-a-uuid",
        )

    assert called is False


@pytest.mark.asyncio
async def test_ingest_task_without_audit_job_id_skips_lifecycle_hooks(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = object()
    called = {"running": False, "progress": False}

    async def fake_sync_source_by_id(*_args, **_kwargs):
        return SimpleNamespace(
            documents_seen=1,
            documents_created=1,
            versions_created=1,
        )

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        called["running"] = True

    async def fake_increment_audit_job_progress(*_args, **_kwargs):
        called["progress"] = True

    monkeypatch.setattr(
        ingest_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        ingest_task_module,
        "sync_source_by_id",
        fake_sync_source_by_id,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "mark_audit_job_running",
        fake_mark_audit_job_running,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "increment_audit_job_progress",
        fake_increment_audit_job_progress,
    )

    result = await ingest_task_module.ingest_task(
        {},
        source_id=str(uuid.uuid4()),
        audit_job_id=None,
    )

    assert called == {"running": False, "progress": False}
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_ingest_task_noops_when_job_already_completed(
    monkeypatch: pytest.MonkeyPatch,
):
    audit_job_uuid = uuid.uuid4()
    completed_job = SimpleNamespace(status="completed", docs_scanned=4)

    class CompletedSession:
        async def get(self, *_args, **_kwargs):
            return completed_job

    async def fail_sync_source_by_id(*_args, **_kwargs):
        raise AssertionError("completed ingest jobs should not sync sources")

    async def fail_mark_running(*_args, **_kwargs):
        raise AssertionError("completed ingest jobs should not restart")

    monkeypatch.setattr(
        ingest_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(CompletedSession()),
    )
    monkeypatch.setattr(
        ingest_task_module,
        "sync_source_by_id",
        fail_sync_source_by_id,
    )
    monkeypatch.setattr(
        ingest_task_module,
        "mark_audit_job_running",
        fail_mark_running,
    )

    source_id = str(uuid.uuid4())
    result = await ingest_task_module.ingest_task(
        {},
        source_id=source_id,
        audit_job_id=str(audit_job_uuid),
    )

    assert result == {
        "status": "completed",
        "source_id": source_id,
        "audit_job_id": str(audit_job_uuid),
        "documents_seen": 4,
        "documents_created": 0,
        "versions_created": 0,
        "already_completed": True,
    }
