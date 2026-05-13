import datetime
import uuid
from typing import Optional

from sqlalchemy import UUID, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sending', 'delivered', 'failed')",
            name="ck_notification_deliveries_status",
        ),
        CheckConstraint(
            "channel IN ('slack', 'email', 'completion_webhook')",
            name="ck_notification_deliveries_channel",
        ),
        CheckConstraint(
            "event_type IN ('alert_created', 'audit_completed')",
            name="ck_notification_deliveries_event_type",
        ),
        CheckConstraint(
            "attempts >= 0 AND attempts <= 5",
            name="ck_notification_deliveries_attempts_range",
        ),
        CheckConstraint(
            "alert_id IS NOT NULL OR audit_job_id IS NOT NULL",
            name="ck_notification_deliveries_parent_present",
        ),
        Index(
            "ix_notification_deliveries_audit_status_created",
            "audit_job_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_notification_deliveries_alert_channel",
            "alert_id",
            "channel",
        ),
        Index(
            "uq_notification_deliveries_idempotency_key",
            "idempotency_key",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    audit_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("audit_jobs.id"),
        nullable=True,
    )
    alert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("alerts.id"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    delivered_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
