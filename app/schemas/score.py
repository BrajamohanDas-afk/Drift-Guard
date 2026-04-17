import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class ScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    score: float
    breakdown: dict | None = None
    scored_at: datetime.datetime


class ScoreListMeta(BaseModel):
    total: int
    page: int
    per_page: int


class ScoreListResponse(BaseModel):
    data: list[ScoreResponse]
    meta: ScoreListMeta
