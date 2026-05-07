import datetime
import uuid

import pytest

from app.models.alert import Alert
from app.models.document import Document
from app.models.entity import Entity
from app.models.runbook_score import RunbookScore
from app.services.scoring.scoring_service import ScoreInputs, ScoringService


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)

    def first(self):
        return self._values[0] if self._values else None


class _FakeExecuteResult:
    def __init__(self, values, scalar_value=None):
        self._values = list(values)
        self._scalar_value = scalar_value

    def scalars(self):
        return _FakeScalarResult(self._values)

    def scalar(self):
        return self._scalar_value


class _FakeAsyncSession:
    def __init__(self, *, execute_results=None, get_results=None):
        self._execute_results = list(execute_results or [])
        self._get_results = dict(get_results or {})

        self.executed_queries = []
        self.get_calls = []
        self.added = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.refresh_calls = 0

    async def execute(self, query):
        self.executed_queries.append(query)
        if not self._execute_results:
            raise AssertionError("No fake execute result available")
        return self._execute_results.pop(0)

    async def get(self, model, key):
        self.get_calls.append((model, key))
        return self._get_results.get((model, key))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_calls += 1

    async def commit(self):
        self.commit_calls += 1

    async def refresh(self, _obj):
        self.refresh_calls += 1


def _make_alert(document_id: uuid.UUID, severity: str) -> Alert:
    return Alert(
        document_id=document_id,
        rule_type="rule",
        severity=severity,
        message=f"{severity} alert",
        evidence={},
        resolved=False,
    )


def _make_entity(
    document_id: uuid.UUID, document_version_id: uuid.UUID, entity_type: str
) -> Entity:
    return Entity(
        document_id=document_id,
        document_version_id=document_version_id,
        entity_type=entity_type,
        value=f"{entity_type}-value",
        context="",
    )


def _compiled_sql(query) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True})).lower()


def test_calculate_breakdown_applies_alert_deductions():
    service = ScoringService()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    inputs = ScoreInputs(
        document_id=document_id,
        unresolved_alerts=[
            _make_alert(document_id, "critical"),
            _make_alert(document_id, "high"),
            _make_alert(document_id, "medium"),
            _make_alert(document_id, "low"),
        ],
        latest_entities=[
            _make_entity(document_id, version_id, "owner"),
            _make_entity(document_id, version_id, "service"),
            _make_entity(document_id, version_id, "dashboard"),
        ],
    )

    breakdown = service.calculate_breakdown(inputs)

    assert breakdown["base_score"] == 100.0
    assert breakdown["counts"]["alerts"] == {
        "critical": 1,
        "high": 1,
        "medium": 1,
        "low": 1,
    }
    assert breakdown["total_deductions"] == 65.0
    assert breakdown["final_score"] == 35.0


def test_calculate_breakdown_applies_extraction_quality_deductions():
    service = ScoringService()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    inputs = ScoreInputs(
        document_id=document_id,
        unresolved_alerts=[],
        latest_entities=[
            _make_entity(document_id, version_id, "dashboard"),
            _make_entity(document_id, version_id, "cluster"),
        ],
    )

    breakdown = service.calculate_breakdown(inputs)

    assert breakdown["counts"]["entities"] == {
        "total": 2,
        "owner_present": False,
        "service_present": False,
    }
    assert breakdown["deduction_totals"]["alerts"] == 0.0
    assert breakdown["deduction_totals"]["extraction_quality"] == 30.0
    assert breakdown["final_score"] == 70.0


def test_calculate_breakdown_clamps_score_to_zero():
    service = ScoringService()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    inputs = ScoreInputs(
        document_id=document_id,
        unresolved_alerts=[_make_alert(document_id, "critical") for _ in range(4)],
        latest_entities=[
            _make_entity(document_id, version_id, "owner"),
            _make_entity(document_id, version_id, "service"),
            _make_entity(document_id, version_id, "dashboard"),
        ],
    )

    breakdown = service.calculate_breakdown(inputs)

    assert breakdown["total_deductions"] == 120.0
    assert breakdown["final_score"] == 0.0


def test_calculate_breakdown_has_expected_shape():
    service = ScoringService()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    inputs = ScoreInputs(
        document_id=document_id,
        unresolved_alerts=[_make_alert(document_id, "low")],
        latest_entities=[
            _make_entity(document_id, version_id, "owner"),
            _make_entity(document_id, version_id, "service"),
            _make_entity(document_id, version_id, "dashboard"),
        ],
    )

    breakdown = service.calculate_breakdown(inputs)

    assert set(breakdown.keys()) == {
        "base_score",
        "counts",
        "deductions",
        "deduction_totals",
        "total_deductions",
        "final_score",
    }
    assert all(
        set(deduction.keys()) == {"category", "reason", "count", "weight", "amount"}
        for deduction in breakdown["deductions"]
    )


@pytest.mark.asyncio
async def test_compute_score_inputs_fetches_alerts_and_latest_entities():
    service = ScoringService()
    document_id = uuid.uuid4()
    latest_version_id = uuid.uuid4()
    document = Document(
        id=document_id,
        title="payments runbook",
        latest_version_id=latest_version_id,
    )
    alert = _make_alert(document_id, "high")
    entities = [
        _make_entity(document_id, latest_version_id, "owner"),
        _make_entity(document_id, latest_version_id, "service"),
        _make_entity(document_id, latest_version_id, "dashboard"),
    ]
    session = _FakeAsyncSession(
        execute_results=[_FakeExecuteResult([alert]), _FakeExecuteResult(entities)],
        get_results={(Document, document_id): document},
    )

    inputs = await service.compute_score_inputs(session, document_id=document_id)

    assert inputs.document_id == document_id
    assert inputs.unresolved_alerts == [alert]
    assert inputs.latest_entities == entities
    assert len(session.executed_queries) == 2
    assert session.get_calls == [(Document, document_id)]


@pytest.mark.asyncio
async def test_compute_score_inputs_rejects_deleted_document():
    service = ScoringService()
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        title="deleted runbook",
        is_deleted=True,
    )
    session = _FakeAsyncSession(get_results={(Document, document_id): document})

    with pytest.raises(ValueError, match="Document not found"):
        await service.compute_score_inputs(session, document_id=document_id)

    assert session.executed_queries == []


@pytest.mark.asyncio
async def test_persist_score_snapshot_rounds_and_persists():
    service = ScoringService()
    document_id = uuid.uuid4()
    session = _FakeAsyncSession()
    breakdown = {
        "base_score": 100.0,
        "counts": {},
        "deductions": [],
        "deduction_totals": {},
        "total_deductions": 33.333,
        "final_score": 66.667,
    }

    saved = await service.persist_score_snapshot(
        session,
        document_id=document_id,
        score=66.667,
        breakdown=breakdown,
    )

    assert saved in session.added
    assert isinstance(saved, RunbookScore)
    assert saved.document_id == document_id
    assert float(saved.score) == 66.67
    assert saved.breakdown == breakdown
    assert session.flush_calls == 1
    assert session.commit_calls == 1
    assert session.refresh_calls == 1


@pytest.mark.asyncio
async def test_get_latest_score_returns_latest_score():
    service = ScoringService()
    document_id = uuid.uuid4()
    latest = RunbookScore(
        id=uuid.uuid4(),
        document_id=document_id,
        score=91.25,
        breakdown={"final_score": 91.25},
        scored_at=datetime.datetime.now(datetime.timezone.utc),
    )
    session = _FakeAsyncSession(execute_results=[_FakeExecuteResult([latest])])

    result = await service.get_latest_score(session, document_id=document_id)

    assert result is latest
    assert len(session.executed_queries) == 1
    compiled = _compiled_sql(session.executed_queries[0])
    assert "join documents" in compiled
    assert "documents.is_deleted is false" in compiled


@pytest.mark.asyncio
async def test_list_latest_scores_per_document_returns_latest_rows():
    service = ScoringService()
    now = datetime.datetime.now(datetime.timezone.utc)
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    latest_scores = [
        RunbookScore(
            id=uuid.uuid4(),
            document_id=doc_a,
            score=88.0,
            breakdown={"final_score": 88.0},
            scored_at=now,
        ),
        RunbookScore(
            id=uuid.uuid4(),
            document_id=doc_b,
            score=73.0,
            breakdown={"final_score": 73.0},
            scored_at=now,
        ),
    ]
    session = _FakeAsyncSession(execute_results=[_FakeExecuteResult(latest_scores)])

    result = await service.list_latest_scores_per_document(session)

    assert result == latest_scores
    assert len(session.executed_queries) == 1
    compiled = _compiled_sql(session.executed_queries[0])
    assert "join documents" in compiled
    assert "documents.is_deleted is false" in compiled


@pytest.mark.asyncio
async def test_list_latest_scores_per_document_paginated_returns_page_and_total():
    service = ScoringService()
    now = datetime.datetime.now(datetime.timezone.utc)
    paged_scores = [
        RunbookScore(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            score=91.0,
            breakdown={"final_score": 91.0},
            scored_at=now,
        )
    ]
    session = _FakeAsyncSession(
        execute_results=[
            _FakeExecuteResult([], scalar_value=3),
            _FakeExecuteResult(paged_scores),
        ]
    )

    scores, total = await service.list_latest_scores_per_document_paginated(
        session,
        page=2,
        per_page=2,
    )

    assert scores == paged_scores
    assert total == 3
    assert len(session.executed_queries) == 2
    compiled_count = _compiled_sql(session.executed_queries[0])
    compiled_list = _compiled_sql(session.executed_queries[1])
    assert "join documents" in compiled_count
    assert "join documents" in compiled_list
    assert "documents.is_deleted is false" in compiled_count
    assert "documents.is_deleted is false" in compiled_list


@pytest.mark.asyncio
async def test_list_latest_scores_per_document_paginated_validates_inputs():
    service = ScoringService()
    session = _FakeAsyncSession()

    with pytest.raises(ValueError, match="page must be >= 1"):
        await service.list_latest_scores_per_document_paginated(
            session,
            page=0,
            per_page=20,
        )

    with pytest.raises(ValueError, match="per_page must be between 1 and 100"):
        await service.list_latest_scores_per_document_paginated(
            session,
            page=1,
            per_page=101,
        )
