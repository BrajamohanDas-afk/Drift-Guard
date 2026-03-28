import datetime
import uuid
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict

class GitSourceConfig(BaseModel):
    repo_url: str
    branch: str = "main"
    path_filter: Optional[str] = None

class SourceCreate(BaseModel):
    name: str
    type: Literal["git"]
    config: GitSourceConfig

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