import datetime
import importlib
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

score_task_module = importlib.import_module("app.workers.score_task")


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


@pytest.mark.asyncio
async def test_score_task_scores_document_and_updates_audit_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = object()
    captured = {}
    transitions: list[tuple[str, uuid.UUID]] = []
    scored_at = datetime.datetime(2026, 4, 18, 12, 0, tzinfo=datetime.timezone.utc)
    score_id = uuid.uuid4()

    class _FakeScoringService:
        async def score_document(self, db, *, document_id):
            captured["db"] = db
            captured["document_id"] = document_id
            return SimpleNamespace(
                id=score_id,
                score=Decimal("88.50"),
                scored_at=scored_at,
            )

    async def fake_mark_audit_job_running(db, *, audit_job_id):
        assert db is fake_session
        transitions.append(("running", audit_job_id))

    monkeypatch.setattr(
        score_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        score_task_module,
        "scoring_service",
        _FakeScoringService(),
    )
    monkeypatch.setattr(
        score_task_module,
        "mark_audit_job_running",
        fake_mark_audit_job_running,
    )

    document_id = str(uuid.uuid4())
    audit_job_id = str(uuid.uuid4())
    result = await score_task_module.score_task(
        {},
        document_id=document_id,
        audit_job_id=audit_job_id,
    )

    assert captured["db"] is fake_session
    assert captured["document_id"] == uuid.UUID(document_id)
    assert transitions == [("running", uuid.UUID(audit_job_id))]
    assert result == {
        "status": "completed",
        "document_id": document_id,
        "audit_job_id": audit_job_id,
        "score_id": str(score_id),
        "score": 88.5,
        "scored_at": scored_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_score_task_rejects_invalid_document_id(
    monkeypatch: pytest.MonkeyPatch,
):
    called = False

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        score_task_module, "mark_audit_job_running", fake_mark_audit_job_running
    )

    with pytest.raises(ValueError):
        await score_task_module.score_task({}, document_id="not-a-uuid")

    assert called is False


@pytest.mark.asyncio
async def test_score_task_rejects_invalid_audit_job_id(
    monkeypatch: pytest.MonkeyPatch,
):
    called = False

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        score_task_module, "mark_audit_job_running", fake_mark_audit_job_running
    )

    with pytest.raises(ValueError):
        await score_task_module.score_task(
            {},
            document_id=str(uuid.uuid4()),
            audit_job_id="not-a-uuid",
        )

    assert called is False


@pytest.mark.asyncio
async def test_score_task_marks_audit_failed_on_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = object()
    failure_calls = []
    events = []

    class _FailingScoringService:
        async def score_document(self, db, *, document_id):
            assert db is fake_session
            assert isinstance(document_id, uuid.UUID)
            events.append("score")
            raise RuntimeError("scoring failed")

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        events.append("running")
        return None

    async def fake_mark_failed_best_effort(audit_job_id, error):
        failure_calls.append((audit_job_id, error))

    monkeypatch.setattr(
        score_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        score_task_module,
        "scoring_service",
        _FailingScoringService(),
    )
    monkeypatch.setattr(
        score_task_module,
        "mark_audit_job_running",
        fake_mark_audit_job_running,
    )
    monkeypatch.setattr(
        score_task_module,
        "_mark_audit_job_failed_best_effort",
        fake_mark_failed_best_effort,
    )

    audit_job_uuid = uuid.uuid4()
    with pytest.raises(RuntimeError, match="scoring failed"):
        await score_task_module.score_task(
            {},
            document_id=str(uuid.uuid4()),
            audit_job_id=str(audit_job_uuid),
        )

    assert events == ["running", "score"]
    assert failure_calls == [
        (audit_job_uuid, "score_task failed for document_id=<redacted>")
    ]


@pytest.mark.asyncio
async def test_score_task_without_audit_job_id_skips_lifecycle_hooks(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = object()
    called = {"running": False}
    score_id = uuid.uuid4()
    scored_at = datetime.datetime(2026, 4, 18, 12, 0, tzinfo=datetime.timezone.utc)

    class _FakeScoringService:
        async def score_document(self, db, *, document_id):
            assert db is fake_session
            assert isinstance(document_id, uuid.UUID)
            return SimpleNamespace(
                id=score_id,
                score=Decimal("75.00"),
                scored_at=scored_at,
            )

    async def fake_mark_audit_job_running(*_args, **_kwargs):
        called["running"] = True

    monkeypatch.setattr(
        score_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        score_task_module,
        "scoring_service",
        _FakeScoringService(),
    )
    monkeypatch.setattr(
        score_task_module,
        "mark_audit_job_running",
        fake_mark_audit_job_running,
    )

    result = await score_task_module.score_task(
        {},
        document_id=str(uuid.uuid4()),
        audit_job_id=None,
    )

    assert called == {"running": False}
    assert result["status"] == "completed"
