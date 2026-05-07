import datetime
import uuid
from typing import Optional

from sqlalchemy import UUID, CheckConstraint, DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

AUDIT_JOB_STATUS_CHECK = "status IN ('pending', 'running', 'completed', 'failed')"


class AuditJob(Base):
    __tablename__ = "audit_jobs"
    __table_args__ = (
        CheckConstraint(AUDIT_JOB_STATUS_CHECK, name="ck_audit_jobs_status"),
        Index("ix_audit_jobs_status_started", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    triggered_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text,
        default="pending",
        server_default="pending",
        nullable=False,
    )
    docs_scanned: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    alerts_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

