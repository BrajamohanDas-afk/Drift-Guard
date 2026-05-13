import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.alert import Alert
from app.models.audit_job import AuditJob
from app.models.notification_delivery import NotificationDelivery
from app.services.alerting.notification_service import NotificationService


async def test_notification_service_creates_idempotent_delivery_rows():
    async with AsyncSessionLocal() as session:
        audit_job = AuditJob(id=uuid.uuid4(), triggered_by="manual", status="completed")
        alert = Alert(
            id=uuid.uuid4(),
            document_id=None,
            rule_type="owner_missing",
            severity="high",
            message="Owner is missing from runbook metadata",
            evidence={"missing_entity_type": "owner"},
        )
        session.add_all([audit_job, alert])
        await session.commit()
        await session.refresh(audit_job)
        await session.refresh(alert)

        service = NotificationService(
            channels="email",
            min_severity="medium",
            email_sink_path="C:/tmp/drift-guard-test-notifications.jsonl",
        )

        first = await service.create_audit_notifications(
            session,
            audit_job=audit_job,
            created_alerts=[alert],
            audit_summary={"alerts_created": 1},
        )
        second = await service.create_audit_notifications(
            session,
            audit_job=audit_job,
            created_alerts=[alert],
            audit_summary={"alerts_created": 1},
        )

        assert [delivery.id for delivery in first] == [
            delivery.id for delivery in second
        ]

        result = await session.execute(select(NotificationDelivery))
        deliveries = list(result.scalars().all())
        assert len(deliveries) == 1
        assert deliveries[0].status == "pending"
        assert deliveries[0].attempts == 0
        assert deliveries[0].channel == "email"
        assert deliveries[0].event_type == "alert_created"
