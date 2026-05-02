import uuid

import pytest

from app.models.audit_job import AuditJob
from app.services.audit.audit_job_service import (
    AuditJobNotFoundError,
    AuditJobStateError,
    AuditJobValidationError,
    create_audit_job,
    increment_audit_job_progress,
    mark_audit_job_completed,
    mark_audit_job_failed,
    mark_audit_job_running,
)


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeAsyncSession:
    def __init__(self, *, jobs: dict[uuid.UUID, AuditJob] | None = None):
        self.jobs = dict(jobs or {})
        self.added: list[AuditJob] = []
        self.get_calls: list[tuple[object, uuid.UUID]] = []
        self.commit_calls = 0
        self.refresh_calls = 0

    async def get(self, model, key):
        self.get_calls.append((model, key))
        return self.jobs.get(key)

    def add(self, obj):
        self.added.append(obj)
        if obj.id is not None:
            self.jobs[obj.id] = obj

    async def commit(self):
        self.commit_calls += 1

    async def refresh(self, _obj):
        self.refresh_calls += 1


def _make_job(
    *,
    status: str = "pending",
    docs_scanned: int | None = 0,
    alerts_created: int | None = 0,
) -> AuditJob:
    return AuditJob(
        id=uuid.uuid4(),
        triggered_by="system",
        status=status,
        docs_scanned=docs_scanned,
        alerts_created=alerts_created,
    )


@pytest.mark.asyncio
async def test_create_audit_job_initializes_pending_lifecycle():
    session = _FakeAsyncSession()

    job = await create_audit_job(session, triggered_by="manual")

    assert job in session.added
    assert job.id is not None
    assert job.triggered_by == "manual"
    assert job.status == "pending"
    assert job.docs_scanned == 0
    assert job.alerts_created == 0
    assert job.started_at is None
    assert job.completed_at is None
    assert session.commit_calls == 1
    assert session.refresh_calls == 1


@pytest.mark.asyncio
async def test_mark_audit_job_running_sets_started_at():
    job = _make_job(status="pending")
    session = _FakeAsyncSession(jobs={job.id: job})

    updated = await mark_audit_job_running(session, audit_job_id=job.id)

    assert updated.status == "running"
    assert updated.started_at is not None
    assert updated.docs_scanned == 0
    assert updated.alerts_created == 0
    assert session.commit_calls == 1
    assert session.refresh_calls == 1


@pytest.mark.asyncio
async def test_increment_audit_job_progress_updates_counters():
    job = _make_job(status="running", docs_scanned=1, alerts_created=2)
    session = _FakeAsyncSession(jobs={job.id: job})

    updated = await increment_audit_job_progress(
        session,
        audit_job_id=job.id,
        docs_scanned_delta=3,
        alerts_created_delta=4,
    )

    assert updated.status == "running"
    assert updated.docs_scanned == 4
    assert updated.alerts_created == 6
    assert updated.started_at is not None
    assert session.commit_calls == 1
    assert session.refresh_calls == 1


@pytest.mark.asyncio
async def test_increment_progress_rejects_negative_deltas():
    job = _make_job(status="running")
    session = _FakeAsyncSession(jobs={job.id: job})

    with pytest.raises(AuditJobValidationError, match="docs_scanned_delta"):
        await increment_audit_job_progress(
            session,
            audit_job_id=job.id,
            docs_scanned_delta=-1,
        )

    with pytest.raises(AuditJobValidationError, match="alerts_created_delta"):
        await increment_audit_job_progress(
            session,
            audit_job_id=job.id,
            alerts_created_delta=-1,
        )


@pytest.mark.asyncio
async def test_mark_audit_job_completed_sets_terminal_state():
    job = _make_job(status="running")
    session = _FakeAsyncSession(jobs={job.id: job})

    updated = await mark_audit_job_completed(session, audit_job_id=job.id)

    assert updated.status == "completed"
    assert updated.completed_at is not None
    assert updated.error is None
    assert session.commit_calls == 1
    assert session.refresh_calls == 1


@pytest.mark.asyncio
async def test_mark_audit_job_failed_sets_terminal_state_and_error():
    job = _make_job(status="running")
    session = _FakeAsyncSession(jobs={job.id: job})

    updated = await mark_audit_job_failed(
        session,
        audit_job_id=job.id,
        error="worker failed",
    )

    assert updated.status == "failed"
    assert updated.completed_at is not None
    assert updated.error == "worker failed"
    assert session.commit_calls == 1
    assert session.refresh_calls == 1


@pytest.mark.asyncio
async def test_terminal_transitions_are_rejected():
    completed = _make_job(status="completed")
    failed = _make_job(status="failed")
    session = _FakeAsyncSession(jobs={completed.id: completed, failed.id: failed})

    with pytest.raises(AuditJobStateError):
        await mark_audit_job_running(session, audit_job_id=completed.id)

    resumed = await mark_audit_job_running(session, audit_job_id=failed.id)
    assert resumed.status == "running"
    assert resumed.completed_at is None
    assert resumed.error is None


@pytest.mark.asyncio
async def test_missing_audit_job_raises_not_found():
    session = _FakeAsyncSession()

    with pytest.raises(AuditJobNotFoundError, match="Audit job not found"):
        await mark_audit_job_running(session, audit_job_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_mark_completed_rejects_failed_job():
    job = _make_job(status="failed")
    session = _FakeAsyncSession(jobs={job.id: job})

    with pytest.raises(AuditJobStateError):
        await mark_audit_job_completed(session, audit_job_id=job.id)


@pytest.mark.asyncio
async def test_mark_failed_rejects_completed_job():
    job = _make_job(status="completed")
    session = _FakeAsyncSession(jobs={job.id: job})

    with pytest.raises(AuditJobStateError):
        await mark_audit_job_failed(
            session,
            audit_job_id=job.id,
            error="worker failed",
        )


@pytest.mark.asyncio
async def test_terminal_methods_are_idempotent():
    completed = _make_job(status="completed")
    failed = _make_job(status="failed")
    failed.error = "original failure"
    session = _FakeAsyncSession(jobs={completed.id: completed, failed.id: failed})

    same_completed = await mark_audit_job_completed(session, audit_job_id=completed.id)
    assert same_completed.status == "completed"

    same_failed = await mark_audit_job_failed(
        session,
        audit_job_id=failed.id,
        error="new failure",
    )
    assert same_failed.status == "failed"
    assert same_failed.error == "original failure"
