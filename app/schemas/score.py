import uuid
import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    score: float
    breakdown: Optional[dict] = None
    scored_at: datetime.datetime
