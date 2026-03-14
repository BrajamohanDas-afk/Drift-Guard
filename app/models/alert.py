import uuid
import datetime
from typing import Optional
from app.models.base import Base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import UUID, DateTime, Text, ForeignKey, Boolean

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Optional[dict]] = mapped_column(JSONB)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
