import uuid
import datetime
from typing import Optional
from app.models.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import UUID, DateTime, Text, Integer

class AuditJob(Base):
    __tablename__ = "audit_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    triggered_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, default='pending', nullable=True)
    docs_scanned: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    alerts_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

