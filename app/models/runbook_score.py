import uuid
import datetime
from typing import Optional
from app.models.base import Base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import UUID, DateTime, ForeignKey, Numeric

class RunbookScore(Base):
    __tablename__ = "runbook_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5,2), nullable=False)
    breakdown: Mapped[Optional[dict]] = mapped_column(JSONB)
    scored_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )