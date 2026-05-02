import importlib
import uuid
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.alert import Alert
from app.models.audit_job import AuditJob
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.entity import Entity
from app.models.runbook_score import RunbookScore
from app.services.audit.audit_job_service import create_audit_job
from app.workers.queue import QueueEnqueueError

audit_api_module = importlib.import_module("app.api.v1.audit")

TEST_HEADERS = {"x-api-key": settings.api_key}


async def test_run_audit_creates_job_and_enqueues_worker(
    monkeypatch,
):
    enqueue_calls = []

    async def fake_enqueue_audit_run_task(*, audit_job_id, job_id):
        enqueue_calls.append((audit_job_id, job_id))
        return object()

    monkeypatch.setattr(
        audit_api_module,
        "enqueue_audit_run_task",
        fake_enqueue_audit_run_task,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/audit/run", headers=TEST_HEADERS)

    assert response.status_code == 202
    payload = response.json()
    audit_job_id = uuid.UUID(payload["id"])
    assert payload["triggered_by"] == "manual"
    assert payload["status"] == "pending"
    assert payload["docs_scanned"] == 0
    assert payload["alerts_created"] == 0
    assert enqueue_calls == [
        (str(audit_job_id), f"audit-run:{audit_job_id}"),
    ]

    async with AsyncSessionLocal() as session:
        job = await session.get(AuditJob, audit_job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.triggered_by == "manual"


async def test_run_audit_marks_job_failed_when_enqueue_fails(monkeypatch):
    async def fake_enqueue_audit_run_task(**_kwargs):
        raise QueueEnqueueError("queue unavailable")

    monkeypatch.setattr(
        audit_api_module,
        "enqueue_audit_run_task",
        fake_enqueue_audit_run_task,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/audit/run",
            headers=TEST_HEADERS,
            json={"triggered_by": "swagger"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Failed to enqueue audit run"

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AuditJob))
        job = result.scalars().one()
        assert job.triggered_by == "swagger"
        assert job.status == "failed"
        assert job.error == "Failed to enqueue audit run"


async def test_audit_jobs_list_detail_filter_and_auth(monkeypatch):
    async def fake_enqueue_audit_run_task(**_kwargs):
        return object()

    monkeypatch.setattr(
        audit_api_module,
        "enqueue_audit_run_task",
        fake_enqueue_audit_run_task,
    )

    async with AsyncSessionLocal() as session:
        pending_job = await create_audit_job(session, triggered_by="manual")
        failed_job = AuditJob(
            id=uuid.uuid4(),
            triggered_by="system",
            status="failed",
            docs_scanned=2,
            alerts_created=0,
            error="boom",
        )
        session.add(failed_job)
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unauthorized = await client.get("/v1/audit/jobs")
        assert unauthorized.status_code == 401

        list_response = await client.get("/v1/audit/jobs", headers=TEST_HEADERS)
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["meta"] == {"total": 2, "page": 1, "per_page": 20}
        assert {item["id"] for item in list_payload["data"]} == {
            str(pending_job.id),
            str(failed_job.id),
        }

        filtered_response = await client.get(
            "/v1/audit/jobs",
            params={"status": "failed"},
            headers=TEST_HEADERS,
        )
        assert filtered_response.status_code == 200
        filtered_payload = filtered_response.json()
        assert filtered_payload["meta"]["total"] == 1
        assert filtered_payload["data"][0]["id"] == str(failed_job.id)

        detail_response = await client.get(
            f"/v1/audit/jobs/{pending_job.id}",
            headers=TEST_HEADERS,
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["id"] == str(pending_job.id)

        missing_response = await client.get(
            f"/v1/audit/jobs/{uuid.uuid4()}",
            headers=TEST_HEADERS,
        )
        assert missing_response.status_code == 404
        assert missing_response.json()["detail"] == "Audit job not found"

        invalid_pagination = await client.get(
            "/v1/audit/jobs",
            params={"page": 0},
            headers=TEST_HEADERS,
        )
        assert invalid_pagination.status_code == 422

        invalid_status = await client.get(
            "/v1/audit/jobs",
            params={"status": "unknown"},
            headers=TEST_HEADERS,
        )
        assert invalid_status.status_code == 422

        invalid_trigger = await client.post(
            "/v1/audit/run",
            json={"triggered_by": ""},
            headers=TEST_HEADERS,
        )
        assert invalid_trigger.status_code == 422


async def test_audit_report_returns_global_summary():
    started_at = datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        session.add(
            AuditJob(
                id=uuid.uuid4(),
                triggered_by="manual",
                status="completed",
                docs_scanned=2,
                alerts_created=2,
                started_at=started_at,
                completed_at=started_at,
            )
        )

        payments_doc = Document(title="payments.md")
        billing_doc = Document(title="billing.md", service_name="billing-api")
        deleted_doc = Document(title="deleted.md", is_deleted=True)
        session.add_all([payments_doc, billing_doc, deleted_doc])
        await session.flush()

        payments_version = DocumentVersion(
            document_id=payments_doc.id,
            raw_content="# Payments",
            normalized_content="# Payments",
            content_hash="payments-hash",
            version_number=1,
        )
        billing_version = DocumentVersion(
            document_id=billing_doc.id,
            raw_content="# Billing",
            normalized_content="# Billing",
            content_hash="billing-hash",
            version_number=1,
        )
        session.add_all([payments_version, billing_version])
        await session.flush()
        payments_doc.latest_version_id = payments_version.id
        billing_doc.latest_version_id = billing_version.id

        session.add(
            Entity(
                document_id=payments_doc.id,
                document_version_id=payments_version.id,
                entity_type="service",
                value="payments-api",
                context="service: payments-api",
            )
        )
        session.add_all(
            [
                Alert(
                    document_id=payments_doc.id,
                    rule_type="owner_missing",
                    severity="high",
                    message="Owner missing",
                    evidence={"missing_entity_type": "owner"},
                    resolved=False,
                ),
                Alert(
                    document_id=billing_doc.id,
                    rule_type="dashboard_dead",
                    severity="low",
                    message="Dashboard dead",
                    evidence={"dashboard": "grafana:billing"},
                    resolved=False,
                ),
                Alert(
                    document_id=None,
                    rule_type="global_check",
                    severity="medium",
                    message="Global check failed",
                    evidence={},
                    resolved=False,
                ),
                Alert(
                    document_id=payments_doc.id,
                    rule_type="old_alert",
                    severity="critical",
                    message="Resolved alert",
                    evidence={},
                    resolved=True,
                ),
                Alert(
                    document_id=deleted_doc.id,
                    rule_type="deleted_doc_alert",
                    severity="critical",
                    message="Deleted document alert",
                    evidence={},
                    resolved=False,
                ),
            ]
        )
        session.add_all(
            [
                RunbookScore(
                    document_id=payments_doc.id,
                    score=90.0,
                    breakdown={},
                    scored_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
                ),
                RunbookScore(
                    document_id=payments_doc.id,
                    score=80.0,
                    breakdown={},
                    scored_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                ),
                RunbookScore(
                    document_id=billing_doc.id,
                    score=95.0,
                    breakdown={},
                    scored_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/audit/report", headers=TEST_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "global"
    assert payload["service_name"] is None
    assert payload["latest_audit_job"]["status"] == "completed"
    assert payload["totals"] == {"documents": 2, "unresolved_alerts": 3}
    assert payload["alerts_by_severity"]["critical"] == 0
    assert payload["alerts_by_severity"]["high"] == 1
    assert payload["alerts_by_severity"]["medium"] == 1
    assert payload["alerts_by_severity"]["low"] == 1
    assert payload["score_summary"] == {
        "documents_scored": 2,
        "average_score": 87.5,
    }
    assert payload["lowest_scoring_documents"][0]["document_id"] == str(
        payments_doc.id
    )
    assert payload["lowest_scoring_documents"][0]["score"] == 80.0


async def test_service_audit_report_filters_by_latest_service_entity_and_auth():
    async with AsyncSessionLocal() as session:
        payments_doc = Document(title="payments.md")
        billing_doc = Document(title="billing.md", service_name="billing-api")
        stale_entity_doc = Document(title="stale-payments.md")
        explicit_service_doc = Document(
            title="explicit-service.md",
            service_name=" Payments-API ",
        )
        session.add_all(
            [payments_doc, billing_doc, stale_entity_doc, explicit_service_doc]
        )
        await session.flush()

        payments_version = DocumentVersion(
            document_id=payments_doc.id,
            raw_content="# Payments",
            normalized_content="# Payments",
            content_hash="payments-service-hash",
            version_number=1,
        )
        stale_payments_version = DocumentVersion(
            document_id=stale_entity_doc.id,
            raw_content="# Stale Payments",
            normalized_content="# Stale Payments",
            content_hash="stale-payments-service-hash",
            version_number=1,
        )
        stale_platform_version = DocumentVersion(
            document_id=stale_entity_doc.id,
            raw_content="# Platform",
            normalized_content="# Platform",
            content_hash="stale-platform-service-hash",
            version_number=2,
        )
        session.add_all(
            [payments_version, stale_payments_version, stale_platform_version]
        )
        await session.flush()
        payments_doc.latest_version_id = payments_version.id
        stale_entity_doc.latest_version_id = stale_platform_version.id

        session.add_all(
            [
                Entity(
                    document_id=payments_doc.id,
                    document_version_id=payments_version.id,
                    entity_type="service",
                    value="payments-api",
                    context="service: payments-api",
                ),
                Entity(
                    document_id=stale_entity_doc.id,
                    document_version_id=stale_payments_version.id,
                    entity_type="service",
                    value="payments-api",
                    context="service: payments-api",
                ),
                Entity(
                    document_id=stale_entity_doc.id,
                    document_version_id=stale_platform_version.id,
                    entity_type="service",
                    value="platform-api",
                    context="service: platform-api",
                ),
            ]
        )
        session.add_all(
            [
                Alert(
                    document_id=payments_doc.id,
                    rule_type="owner_missing",
                    severity="high",
                    message="Owner missing",
                    evidence={},
                    resolved=False,
                ),
                Alert(
                    document_id=billing_doc.id,
                    rule_type="dashboard_dead",
                    severity="low",
                    message="Dashboard dead",
                    evidence={},
                    resolved=False,
                ),
                Alert(
                    document_id=stale_entity_doc.id,
                    rule_type="stale_entity_alert",
                    severity="critical",
                    message="Stale entity alert",
                    evidence={},
                    resolved=False,
                ),
                Alert(
                    document_id=explicit_service_doc.id,
                    rule_type="explicit_service_alert",
                    severity="medium",
                    message="Explicit service alert",
                    evidence={},
                    resolved=False,
                ),
                RunbookScore(
                    document_id=payments_doc.id,
                    score=82.0,
                    breakdown={},
                    scored_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                ),
                RunbookScore(
                    document_id=billing_doc.id,
                    score=97.0,
                    breakdown={},
                    scored_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                ),
                RunbookScore(
                    document_id=stale_entity_doc.id,
                    score=10.0,
                    breakdown={},
                    scored_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                ),
                RunbookScore(
                    document_id=explicit_service_doc.id,
                    score=88.0,
                    breakdown={},
                    scored_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unauthorized = await client.get("/v1/audit/report")
        assert unauthorized.status_code == 401

        service_response = await client.get(
            "/v1/audit/service/payments-api",
            headers=TEST_HEADERS,
        )
        missing_response = await client.get(
            "/v1/audit/service/missing-service",
            headers=TEST_HEADERS,
        )

    assert service_response.status_code == 200
    service_payload = service_response.json()
    assert service_payload["scope"] == "service"
    assert service_payload["service_name"] == "payments-api"
    assert service_payload["totals"] == {"documents": 2, "unresolved_alerts": 2}
    assert service_payload["alerts_by_severity"]["high"] == 1
    assert service_payload["alerts_by_severity"]["low"] == 0
    assert service_payload["alerts_by_severity"]["medium"] == 1
    assert service_payload["alerts_by_severity"]["critical"] == 0
    assert service_payload["score_summary"] == {
        "documents_scored": 2,
        "average_score": 85.0,
    }
    assert service_payload["lowest_scoring_documents"][0]["document_id"] == str(
        payments_doc.id
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Service not found"
