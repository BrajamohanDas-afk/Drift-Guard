import uuid

import pytest

from app.models.alert import Alert
from app.services.drift.alert_service import AlertService
from app.services.drift.rules.base import DriftAlertDraft


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, alerts):
        self.alerts = alerts
        self.commit_calls = 0
        self.refresh_calls = []

    async def execute(self, _query):
        return _FakeResult(self.alerts)

    async def commit(self):
        self.commit_calls += 1

    async def refresh(self, alert):
        self.refresh_calls.append(alert)

    async def rollback(self):
        pass


class _FakeScoringService:
    def __init__(self):
        self.calls = []

    async def score_document(self, _db, *, document_id):
        self.calls.append(document_id)


def _alert(
    *,
    document_id: uuid.UUID,
    evidence: dict,
    rule_type: str = "owner_missing",
) -> Alert:
    return Alert(
        id=uuid.uuid4(),
        document_id=document_id,
        rule_type=rule_type,
        severity="high",
        message="Owner is missing",
        evidence=evidence,
        resolved=False,
        resolved_at=None,
    )


def _draft(
    *,
    document_id: uuid.UUID,
    evidence: dict,
    rule_type: str = "owner_missing",
) -> DriftAlertDraft:
    return DriftAlertDraft(
        document_id=document_id,
        rule_type=rule_type,
        severity="high",
        message="Owner is missing",
        evidence=evidence,
    )


@pytest.mark.asyncio
async def test_reconcile_stale_alerts_resolves_missing_fingerprints():
    document_id = uuid.uuid4()
    stale_alert = _alert(document_id=document_id, evidence={"owner": "missing"})
    session = _FakeSession([stale_alert])
    scoring_service = _FakeScoringService()
    service = AlertService()
    service._scoring_service = scoring_service

    resolved = await service.reconcile_stale_alerts(
        session,
        current_alerts=[],
        document_id=document_id,
        rule_types={"owner_missing"},
    )

    assert resolved == [stale_alert]
    assert stale_alert.resolved is True
    assert stale_alert.resolved_at is not None
    assert session.commit_calls == 1
    assert session.refresh_calls == [stale_alert]
    assert scoring_service.calls == [document_id]


@pytest.mark.asyncio
async def test_reconcile_stale_alerts_keeps_current_fingerprints_unresolved():
    document_id = uuid.uuid4()
    current_alert = _alert(document_id=document_id, evidence={"owner": "missing"})
    session = _FakeSession([current_alert])
    scoring_service = _FakeScoringService()
    service = AlertService()
    service._scoring_service = scoring_service

    resolved = await service.reconcile_stale_alerts(
        session,
        current_alerts=[
            _draft(document_id=document_id, evidence={"owner": "missing"})
        ],
        document_id=document_id,
        rule_types={"owner_missing"},
    )

    assert resolved == []
    assert current_alert.resolved is False
    assert current_alert.resolved_at is None
    assert session.commit_calls == 0
    assert scoring_service.calls == []


@pytest.mark.asyncio
async def test_persist_alerts_for_rule_run_returns_created_and_resolved(monkeypatch):
    document_id = uuid.uuid4()
    created_alert = _alert(document_id=document_id, evidence={"owner": "missing"})
    resolved_alert = _alert(
        document_id=document_id,
        evidence={"owner": "formerly_missing"},
    )
    service = AlertService()

    async def fake_persist_alerts(_db, alerts):
        assert alerts == [
            _draft(document_id=document_id, evidence={"owner": "missing"})
        ]
        return [created_alert]

    async def fake_reconcile_stale_alerts(_db, **kwargs):
        assert kwargs["document_id"] == document_id
        assert kwargs["rule_types"] == {"owner_missing"}
        return [resolved_alert]

    monkeypatch.setattr(service, "persist_alerts", fake_persist_alerts)
    monkeypatch.setattr(
        service,
        "reconcile_stale_alerts",
        fake_reconcile_stale_alerts,
    )

    result = await service.persist_alerts_for_rule_run(
        object(),
        [_draft(document_id=document_id, evidence={"owner": "missing"})],
        document_id=document_id,
        rule_types={"owner_missing"},
    )

    assert result.created == [created_alert]
    assert result.resolved == [resolved_alert]
