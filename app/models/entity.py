import uuid
import datetime
from typing import Optional
from app.models.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import UUID, DateTime, Text, ForeignKey

class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id"))
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"),nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text)
    extracted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False
    )