import importlib
import uuid
from types import SimpleNamespace

import pytest

audit_run_task_module = importlib.import_module("app.workers.audit_run_task")


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
async def test_audit_run_task_syncs_sources_and_completes_job(monkeypatch):
    fake_session = _FakeSession()
    audit_job_id = uuid.uuid4()
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    events = []

    async def fake_list_source_ids(db):
        assert db is fake_session
        return [source_a, source_b]

    async def fake_mark_running(db, *, audit_job_id):
        assert db is fake_session
        events.append(("running", audit_job_id))

    async def fake_sync_source_by_id(source_id, *, db):
        assert db is fake_session
        events.append(("sync", source_id))
        return SimpleNamespace(
            documents_seen=2 if source_id == source_a else 3,
            documents_created=1,
            versions_created=1,
        )

    async def fake_increment_progress(
        db, *, audit_job_id, docs_scanned_delta=0, alerts_created_delta=0
    ):
        assert db is fake_session
        events.append(
            ("progress", audit_job_id, docs_scanned_delta, alerts_created_delta)
        )

    async def fake_scan_all_documents(db):
        assert db is fake_session
        events.append(("scan",))
        return SimpleNamespace(
            documents_scanned=4,
            alerts_created=2,
            alerts_resolved=1,
            scores_refreshed=4,
            created_alerts=(),
        )

    async def fake_mark_completed(db, *, audit_job_id):
        assert db is fake_session
        events.append(("completed", audit_job_id))
        return SimpleNamespace(id=audit_job_id)

    async def fake_create_and_enqueue_notifications_best_effort(
        db, *, audit_job, created_alerts, audit_summary
    ):
        assert db is fake_session
        assert audit_job.id == audit_job_id
        assert created_alerts == ()
        events.append(("notifications", audit_summary["alerts_created"]))

    monkeypatch.setattr(
        audit_run_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(audit_run_task_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(
        audit_run_task_module,
        "mark_audit_job_running",
        fake_mark_running,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "sync_source_by_id",
        fake_sync_source_by_id,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "increment_audit_job_progress",
        fake_increment_progress,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "scan_all_documents",
        fake_scan_all_documents,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "mark_audit_job_completed",
        fake_mark_completed,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "_create_and_enqueue_notifications_best_effort",
        fake_create_and_enqueue_notifications_best_effort,
    )

    result = await audit_run_task_module.audit_run_task(
        {},
        audit_job_id=str(audit_job_id),
    )

    assert events == [
        ("running", audit_job_id),
        ("sync", source_a),
        ("sync", source_b),
        ("scan",),
        ("progress", audit_job_id, 4, 2),
        ("completed", audit_job_id),
        ("notifications", 2),
    ]
    assert result == {
        "status": "completed",
        "audit_job_id": str(audit_job_id),
        "sources_seen": 2,
        "documents_seen": 4,
        "documents_created": 2,
        "versions_created": 2,
        "alerts_created": 2,
        "alerts_resolved": 1,
        "scores_refreshed": 4,
    }


@pytest.mark.asyncio
async def test_audit_run_task_completes_when_no_sources(monkeypatch):
    fake_session = _FakeSession()
    audit_job_id = uuid.uuid4()
    events = []

    async def fake_list_source_ids(_db):
        return []

    async def fake_mark_running(_db, *, audit_job_id):
        events.append(("running", audit_job_id))

    async def fake_mark_completed(_db, *, audit_job_id):
        events.append(("completed", audit_job_id))
        return SimpleNamespace(id=audit_job_id)

    async def fake_increment_progress(
        _db, *, audit_job_id, docs_scanned_delta=0, alerts_created_delta=0
    ):
        events.append(
            ("progress", audit_job_id, docs_scanned_delta, alerts_created_delta)
        )

    async def fake_scan_all_documents(_db):
        events.append(("scan",))
        return SimpleNamespace(
            documents_scanned=0,
            alerts_created=0,
            alerts_resolved=0,
            scores_refreshed=0,
            created_alerts=(),
        )

    async def fake_create_and_enqueue_notifications_best_effort(
        _db, *, audit_job, created_alerts, audit_summary
    ):
        events.append(("notifications", audit_job.id, len(created_alerts)))

    async def fail_sync_source_by_id(*_args, **_kwargs):
        raise AssertionError("sync_source_by_id should not run without sources")

    monkeypatch.setattr(
        audit_run_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(audit_run_task_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(
        audit_run_task_module,
        "mark_audit_job_running",
        fake_mark_running,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "mark_audit_job_completed",
        fake_mark_completed,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "increment_audit_job_progress",
        fake_increment_progress,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "scan_all_documents",
        fake_scan_all_documents,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "sync_source_by_id",
        fail_sync_source_by_id,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "_create_and_enqueue_notifications_best_effort",
        fake_create_and_enqueue_notifications_best_effort,
    )

    result = await audit_run_task_module.audit_run_task(
        {},
        audit_job_id=str(audit_job_id),
    )

    assert events == [
        ("running", audit_job_id),
        ("scan",),
        ("progress", audit_job_id, 0, 0),
        ("completed", audit_job_id),
        ("notifications", audit_job_id, 0),
    ]
    assert result["status"] == "completed"
    assert result["sources_seen"] == 0
    assert result["documents_seen"] == 0


@pytest.mark.asyncio
async def test_audit_run_task_marks_job_failed_on_errors(monkeypatch):
    fake_session = _FakeSession()
    audit_job_id = uuid.uuid4()
    failure_calls = []

    async def fake_list_source_ids(_db):
        return [uuid.uuid4()]

    async def fake_mark_running(*_args, **_kwargs):
        return None

    async def fake_sync_source_by_id(*_args, **_kwargs):
        raise RuntimeError("sync failed")

    async def fake_mark_failed_best_effort(audit_job_id, error):
        failure_calls.append((audit_job_id, error))

    monkeypatch.setattr(
        audit_run_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(audit_run_task_module, "_list_source_ids", fake_list_source_ids)
    monkeypatch.setattr(
        audit_run_task_module,
        "mark_audit_job_running",
        fake_mark_running,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "sync_source_by_id",
        fake_sync_source_by_id,
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "_mark_audit_job_failed_best_effort",
        fake_mark_failed_best_effort,
    )

    with pytest.raises(RuntimeError, match="sync failed"):
        await audit_run_task_module.audit_run_task(
            {},
            audit_job_id=str(audit_job_id),
        )

    assert failure_calls == [(audit_job_id, "audit_run_task failed")]


@pytest.mark.asyncio
async def test_audit_run_task_noops_when_job_already_completed(monkeypatch):
    audit_job_id = uuid.uuid4()
    completed_job = SimpleNamespace(
        status="completed",
        docs_scanned=7,
        alerts_created=3,
    )

    class CompletedSession:
        async def get(self, *_args, **_kwargs):
            return completed_job

    async def fail_mark_running(*_args, **_kwargs):
        raise AssertionError("completed audit jobs should not be restarted")

    async def fail_list_sources(*_args, **_kwargs):
        raise AssertionError("completed audit jobs should not sync sources")

    monkeypatch.setattr(
        audit_run_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(CompletedSession()),
    )
    monkeypatch.setattr(
        audit_run_task_module,
        "mark_audit_job_running",
        fail_mark_running,
    )
    monkeypatch.setattr(audit_run_task_module, "_list_source_ids", fail_list_sources)

    result = await audit_run_task_module.audit_run_task(
        {},
        audit_job_id=str(audit_job_id),
    )

    assert result == {
        "status": "completed",
        "audit_job_id": str(audit_job_id),
        "sources_seen": 0,
        "documents_seen": 7,
        "documents_created": 0,
        "versions_created": 0,
        "alerts_created": 3,
        "alerts_resolved": 0,
        "scores_refreshed": 0,
        "already_completed": True,
    }


@pytest.mark.asyncio
async def test_audit_run_task_rejects_invalid_audit_job_id(monkeypatch):
    called = False

    async def fake_mark_running(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        audit_run_task_module,
        "mark_audit_job_running",
        fake_mark_running,
    )

    with pytest.raises(ValueError):
        await audit_run_task_module.audit_run_task({}, audit_job_id="not-a-uuid")

    assert called is False
