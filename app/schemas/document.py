import uuid
import datetime
from typing import List
from typing import Optional
from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    title: str
    doc_type: Optional[str] = None
    service_name: Optional[str] = None
    
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    doc_type: Optional[str] = None
    service_name: Optional[str] = None
    is_deleted: bool
    deleted_at: Optional[datetime.datetime]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    source_id: Optional[uuid.UUID] = None
    latest_version_id: Optional[uuid.UUID] = None

class DocumentListResponse(BaseModel):
    data: List[DocumentResponse]
    meta: dict