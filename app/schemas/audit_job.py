import uuid
import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AuditJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    triggered_by:Optional[str] = None
    status: Optional[str] = None
    docs_scanned: Optional[int] = None
    alerts_created: Optional[int] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    error: Optional[str] = None
