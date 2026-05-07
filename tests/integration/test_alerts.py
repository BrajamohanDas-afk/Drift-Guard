import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.alert import Alert
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.entity import Entity
from app.models.runbook_score import RunbookScore
from app.services.drift.alert_service import AlertService
from app.services.drift.rules.base import DriftAlertDraft, DriftRuleContext
from app.services.drift.rules.owner_missing_rule import OwnerMissingRule
from app.services.drift.rules_engine import RulesEngine

TEST_HEADERS = {"x-api-key": settings.api_key}


async def test_alert_service_persists_and_deduplicates_unresolved_alerts():
    service = AlertService()
    draft = DriftAlertDraft(
        rule_type="owner_missing",
        severity="high",
        message="Owner missing",
        document_id=None,
        evidence={"owner": None},
    )

    async with AsyncSessionLocal() as session:
        first_created = await service.persist_alerts(session, [draft, draft])
        second_created = await service.persist_alerts(session, [draft])

        assert len(first_created) == 1
        assert second_created == []

        count_result = await session.execute(select(func.count()).select_from(Alert))
        assert int(count_result.scalar() or 0) == 1

        await service.resolve_alert(session, alert=first_created[0])
        third_created = await service.persist_alerts(session, [draft])
        assert len(third_created) == 1

        final_count_result = await session.execute(
            select(func.count()).select_from(Alert)
        )
        assert int(final_count_result.scalar() or 0) == 2


async def test_alert_service_persists_normalized_non_json_evidence():
    service = AlertService()
    draft = DriftAlertDraft(
        rule_type="complex_evidence",
        severity="medium",
        message="Complex evidence persisted",
        document_id=None,
        evidence={
            "members": {"a", "b"},
            "timestamp": datetime(2026, 4, 16, 0, 0, tzinfo=timezone.utc),
        },
    )

    async with AsyncSessionLocal() as session:
        created = await service.persist_alerts(session, [draft])
        assert len(created) == 1
        assert created[0].evidence["members"] == ["a", "b"]
        assert isinstance(created[0].evidence["timestamp"], str)


async def test_alert_endpoints_list_detail_and_resolve():
    service = AlertService()
    async with AsyncSessionLocal() as session:
        created = await service.persist_alerts(
            session,
            [
                DriftAlertDraft(
                    rule_type="owner_missing",
                    severity="high",
                    message="Owner missing",
                    document_id=None,
                    evidence={"missing_entity_type": "owner"},
                ),
                DriftAlertDraft(
                    rule_type="dashboard_dead",
                    severity="medium",
                    message="Dashboard dead",
                    document_id=None,
                    evidence={"dashboard": "grafana:payments"},
                ),
            ],
        )
        assert len(created) == 2
        alert_id = created[0].id

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        list_response = await client.get("/v1/alerts", headers=TEST_HEADERS)
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["meta"]["total"] == 2
        assert len(list_payload["data"]) == 2

        detail_response = await client.get(
            f"/v1/alerts/{alert_id}",
            headers=TEST_HEADERS,
        )
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["id"] == str(alert_id)
        assert detail_payload["resolved"] is False

        resolve_response = await client.patch(
            f"/v1/alerts/{alert_id}/resolve",
            headers=TEST_HEADERS,
        )
        assert resolve_response.status_code == 200
        resolved_payload = resolve_response.json()
        assert resolved_payload["resolved"] is True
        assert resolved_payload["resolved_at"] is not None

        unresolved_list_response = await client.get(
            "/v1/alerts",
            params={"resolved": False},
            headers=TEST_HEADERS,
        )
        assert unresolved_list_response.status_code == 200
        assert unresolved_list_response.json()["meta"]["total"] == 1

        invalid_pagination = await client.get(
            "/v1/alerts",
            params={"page": 0},
            headers=TEST_HEADERS,
        )
        assert invalid_pagination.status_code == 422


async def test_alert_endpoints_not_found_and_auth():
    missing_alert_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unauthorized = await client.get("/v1/alerts")
        assert unauthorized.status_code == 401

        detail_response = await client.get(
            f"/v1/alerts/{missing_alert_id}",
            headers=TEST_HEADERS,
        )
        assert detail_response.status_code == 404
        assert detail_response.json()["detail"] == "Alert not found"

        resolve_response = await client.patch(
            f"/v1/alerts/{missing_alert_id}/resolve",
            headers=TEST_HEADERS,
        )
        assert resolve_response.status_code == 404
        assert resolve_response.json()["detail"] == "Alert not found"


async def test_alert_service_triggers_score_snapshots_for_document_alert_changes():
    service = AlertService()

    async with AsyncSessionLocal() as session:
        document = Document(title="scored-runbook.md")
        session.add(document)
        await session.flush()

        version = DocumentVersion(
            document_id=document.id,
            raw_content="# Runbook",
            normalized_content="# Runbook",
            content_hash="abc123",
            version_number=1,
        )
        session.add(version)
        await session.flush()
        document.latest_version_id = version.id
        session.add_all(
            [
                Entity(
                    document_id=document.id,
                    document_version_id=version.id,
                    entity_type="owner",
                    value="@team-platform",
                    context="owner: @team-platform",
                ),
                Entity(
                    document_id=document.id,
                    document_version_id=version.id,
                    entity_type="service",
                    value="payments-api",
                    context="service: payments-api",
                ),
                Entity(
                    document_id=document.id,
                    document_version_id=version.id,
                    entity_type="dashboard",
                    value="https://grafana.example.com/d/payments",
                    context="dashboard url",
                ),
            ]
        )
        await session.commit()

        created = await service.persist_alerts(
            session,
            [
                DriftAlertDraft(
                    rule_type="dashboard_dead",
                    severity="low",
                    message="Dashboard dead",
                    document_id=document.id,
                    evidence={"dashboard": "https://grafana.example.com/d/payments"},
                )
            ],
        )
        assert len(created) == 1

        first_score = await session.execute(
            select(RunbookScore)
            .where(RunbookScore.document_id == document.id)
            .order_by(RunbookScore.scored_at.desc(), RunbookScore.id.desc())
            .limit(1)
        )
        latest_after_create = first_score.scalars().first()
        assert latest_after_create is not None
        assert float(latest_after_create.score) == 95.0

        duplicate_create = await service.persist_alerts(
            session,
            [
                DriftAlertDraft(
                    rule_type="dashboard_dead",
                    severity="low",
                    message="Dashboard dead",
                    document_id=document.id,
                    evidence={"dashboard": "https://grafana.example.com/d/payments"},
                )
            ],
        )
        assert duplicate_create == []

        scores_after_duplicate_result = await session.execute(
            select(func.count())
            .select_from(RunbookScore)
            .where(RunbookScore.document_id == document.id)
        )
        assert int(scores_after_duplicate_result.scalar() or 0) == 1

        await service.resolve_alert(session, alert=created[0])

        all_scores_result = await session.execute(
            select(RunbookScore)
            .where(RunbookScore.document_id == document.id)
            .order_by(RunbookScore.scored_at.asc(), RunbookScore.id.asc())
        )
        all_scores = list(all_scores_result.scalars().all())
        assert len(all_scores) == 2
        assert float(all_scores[0].score) == 95.0
        assert float(all_scores[1].score) == 100.0


async def test_alert_service_persist_alerts_is_resilient_when_score_refresh_fails():
    service = AlertService()
    service._scoring_service.score_document = AsyncMock(  # type: ignore[attr-defined]
        side_effect=RuntimeError("score refresh failed")
    )

    async with AsyncSessionLocal() as session:
        document = Document(title="best-effort-score-refresh.md")
        session.add(document)
        await session.flush()

        version = DocumentVersion(
            document_id=document.id,
            raw_content="# Runbook",
            normalized_content="# Runbook",
            content_hash="hash-best-effort",
            version_number=1,
        )
        session.add(version)
        await session.flush()
        document.latest_version_id = version.id
        session.add(document)
        await session.commit()

        created = await service.persist_alerts(
            session,
            [
                DriftAlertDraft(
                    rule_type="dashboard_dead",
                    severity="low",
                    message="Dashboard dead",
                    document_id=document.id,
                    evidence={"dashboard": "https://grafana.example.com/d/payments"},
                )
            ],
        )
        assert len(created) == 1

        alerts_result = await session.execute(select(func.count()).select_from(Alert))
        assert int(alerts_result.scalar() or 0) == 1

        scores_result = await session.execute(
            select(func.count()).select_from(RunbookScore)
        )
        assert int(scores_result.scalar() or 0) == 0

        service._scoring_service.score_document.assert_awaited_once()  # type: ignore[attr-defined]


async def test_alert_list_order_uses_id_as_tie_breaker_for_equal_created_at():
    service = AlertService()
    tie_time = datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc)
    lower_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    higher_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                Alert(
                    id=lower_id,
                    document_id=None,
                    rule_type="owner_missing",
                    severity="high",
                    message="Lower id alert",
                    evidence={"missing_entity_type": "owner"},
                    created_at=tie_time,
                    resolved=False,
                ),
                Alert(
                    id=higher_id,
                    document_id=None,
                    rule_type="dashboard_dead",
                    severity="medium",
                    message="Higher id alert",
                    evidence={"dashboard": "grafana:payments"},
                    created_at=tie_time,
                    resolved=False,
                ),
            ]
        )
        await session.commit()

        alerts, total = await service.list_alerts(session, page=1, per_page=10)
        assert total == 2
        assert [alert.id for alert in alerts] == [higher_id, lower_id]


async def test_alert_endpoints_support_filters():
    service = AlertService()
    async with AsyncSessionLocal() as session:
        document_a = Document(title="filters-a.md")
        document_b = Document(title="filters-b.md")
        session.add_all([document_a, document_b])
        await session.flush()

        created = await service.persist_alerts(
            session,
            [
                DriftAlertDraft(
                    rule_type="owner_missing",
                    severity="high",
                    message="Owner missing A",
                    document_id=document_a.id,
                    evidence={"missing_entity_type": "owner"},
                ),
                DriftAlertDraft(
                    rule_type="dashboard_dead",
                    severity="medium",
                    message="Dashboard dead A",
                    document_id=document_a.id,
                    evidence={"dashboard": "grafana:svc-a"},
                ),
                DriftAlertDraft(
                    rule_type="dashboard_dead",
                    severity="high",
                    message="Dashboard dead B",
                    document_id=document_b.id,
                    evidence={"dashboard": "grafana:svc-b"},
                ),
                DriftAlertDraft(
                    rule_type="owner_missing",
                    severity="low",
                    message="Owner missing global",
                    document_id=None,
                    evidence={"missing_entity_type": "owner"},
                ),
            ],
        )
        assert len(created) == 4

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        severity_response = await client.get(
            "/v1/alerts",
            params={"severity": "high"},
            headers=TEST_HEADERS,
        )
        assert severity_response.status_code == 200
        severity_payload = severity_response.json()
        assert severity_payload["meta"]["total"] == 2
        assert all(item["severity"] == "high" for item in severity_payload["data"])

        rule_type_response = await client.get(
            "/v1/alerts",
            params={"rule_type": "dashboard_dead"},
            headers=TEST_HEADERS,
        )
        assert rule_type_response.status_code == 200
        rule_type_payload = rule_type_response.json()
        assert rule_type_payload["meta"]["total"] == 2
        assert all(
            item["rule_type"] == "dashboard_dead" for item in rule_type_payload["data"]
        )

        document_response = await client.get(
            "/v1/alerts",
            params={"document_id": str(document_a.id)},
            headers=TEST_HEADERS,
        )
        assert document_response.status_code == 200
        document_payload = document_response.json()
        assert document_payload["meta"]["total"] == 2
        assert all(
            item["document_id"] == str(document_a.id)
            for item in document_payload["data"]
        )

        combined_response = await client.get(
            "/v1/alerts",
            params={
                "severity": "high",
                "rule_type": "dashboard_dead",
                "document_id": str(document_b.id),
            },
            headers=TEST_HEADERS,
        )
        assert combined_response.status_code == 200
        combined_payload = combined_response.json()
        assert combined_payload["meta"]["total"] == 1
        assert len(combined_payload["data"]) == 1
        combined_item = combined_payload["data"][0]
        assert combined_item["severity"] == "high"
        assert combined_item["rule_type"] == "dashboard_dead"
        assert combined_item["document_id"] == str(document_b.id)


async def test_rules_engine_alert_persistence_creates_score_visible_in_scores_api():
    service = AlertService()
    rules_engine = RulesEngine([OwnerMissingRule()])

    async with AsyncSessionLocal() as session:
        document = Document(title="rules-to-score.md")
        session.add(document)
        await session.flush()

        version = DocumentVersion(
            document_id=document.id,
            raw_content="# Runbook",
            normalized_content="# Runbook",
            content_hash="rules-to-score-hash",
            version_number=1,
        )
        session.add(version)
        await session.flush()
        document.latest_version_id = version.id

        session.add_all(
            [
                Entity(
                    document_id=document.id,
                    document_version_id=version.id,
                    entity_type="service",
                    value="payments-api",
                    context="service: payments-api",
                ),
                Entity(
                    document_id=document.id,
                    document_version_id=version.id,
                    entity_type="dashboard",
                    value="https://grafana.example.com/d/payments",
                    context="dashboard url",
                ),
                Entity(
                    document_id=document.id,
                    document_version_id=version.id,
                    entity_type="command",
                    value="kubectl get pods",
                    context="command example",
                ),
            ]
        )
        await session.commit()

        context = DriftRuleContext(
            document_id=document.id,
            entities=(
                {"entity_type": "service", "value": "payments-api"},
                {
                    "entity_type": "dashboard",
                    "value": "https://grafana.example.com/d/payments",
                },
                {"entity_type": "command", "value": "kubectl get pods"},
            ),
            evidence={},
        )
        evaluated_alerts = rules_engine.evaluate(context)
        assert len(evaluated_alerts) == 1

        created = await service.persist_alerts(session, evaluated_alerts)
        assert len(created) == 1
        assert created[0].rule_type == "owner_missing"

        scores_result = await session.execute(
            select(func.count())
            .select_from(RunbookScore)
            .where(RunbookScore.document_id == document.id)
        )
        assert int(scores_result.scalar() or 0) == 1

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        score_response = await client.get(
            f"/v1/scores/{document.id}",
            headers=TEST_HEADERS,
        )

    assert score_response.status_code == 200
    score_payload = score_response.json()
    assert score_payload["document_id"] == str(document.id)
    assert score_payload["score"] == 65.0
    assert score_payload["breakdown"]["counts"]["alerts"]["high"] == 1
