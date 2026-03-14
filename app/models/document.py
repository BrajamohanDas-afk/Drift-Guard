import uuid
import datetime
from typing import Optional
from app.models.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import UUID, DateTime, Text, ForeignKey,Boolean

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("sources.id"), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[Optional[str]] = mapped_column(Text)
    service_name: Mapped[Optional[str]] = mapped_column(Text)
    latest_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    UUID(as_uuid=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False
    )
    
    
    