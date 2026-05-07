import datetime
import uuid
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints

AuditJobStatus = Literal["pending", "running", "completed", "failed"]
AuditTriggeredBy = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class AuditRunRequest(BaseModel):
    triggered_by: Optional[AuditTriggeredBy] = "manual"


class AuditJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    triggered_by: Optional[str] = None
    status: AuditJobStatus = "pending"
    docs_scanned: Optional[int] = None
    alerts_created: Optional[int] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    error: Optional[str] = None


class AuditJobListMeta(BaseModel):
    total: int
    page: int
    per_page: int


class AuditJobListResponse(BaseModel):
    data: list[AuditJobResponse]
    meta: AuditJobListMeta
