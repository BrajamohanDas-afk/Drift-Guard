import uuid
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.alert import Alert
from app.services.drift.alert_service import AlertService
from app.services.drift.rules.base import DriftAlertDraft

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
