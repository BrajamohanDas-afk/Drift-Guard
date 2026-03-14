import uuid
import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
    

class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    evidence: Optional[dict] = None
    severity: str
    rule_type: str
    document_id: Optional[uuid.UUID] = None
    message: str
    created_at: datetime.datetime
    resolved_at: Optional[datetime.datetime] = None
    resolved: bool
