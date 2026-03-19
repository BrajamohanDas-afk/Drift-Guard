import uuid
import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class SourceCreate(BaseModel):
    name: str
    type: str
    config: dict

class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    last_synced_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime

class SourceListResponse(BaseModel):
    data: List[SourceResponse]
    meta: dict