import uuid
import datetime
from typing import Optional
from app.models.base import Base
from sqlalchemy import UUID, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text,nullable=False)
    type: Mapped[str] = mapped_column(Text,nullable=False)
    config: Mapped[dict] = mapped_column(JSONB,nullable=False)
    last_synced_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )                                              
