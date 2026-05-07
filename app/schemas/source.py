import datetime
import uuid
from typing import Annotated, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.schemas.audit_job import AuditJobStatus

SourceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
RepoUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
]
BranchName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
PathFilter = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1024),
]


def _validate_github_repo_path(repo_path: str) -> None:
    normalized_path = repo_path.strip("/")
    if normalized_path.endswith(".git"):
        normalized_path = normalized_path[:-4]

    path_parts = normalized_path.split("/")
    if len(path_parts) != 2 or not all(path_parts):
        raise ValueError("repo_url must resolve to owner/repo")
    if any(any(char.isspace() for char in part) for part in path_parts):
        raise ValueError("repo_url must resolve to owner/repo")


class GitSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_url: RepoUrl
    branch: BranchName = "main"
    path_filter: Optional[PathFilter] = None

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str) -> str:
        if value.startswith("git@github.com:"):
            _validate_github_repo_path(value.removeprefix("git@github.com:"))
            return value

        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme != "https":
                raise ValueError("repo_url must use https or git@github.com SSH")
            if parsed.netloc.lower() != "github.com":
                raise ValueError("repo_url must point to github.com")
            if parsed.query or parsed.fragment:
                raise ValueError("repo_url must not include query or fragment")
            _validate_github_repo_path(parsed.path)
            return value

        _validate_github_repo_path(value)
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        invalid_chars = set(" ~^:?*[\\")
        if any(char in invalid_chars or ord(char) < 32 for char in value):
            raise ValueError("branch contains invalid git ref characters")
        if (
            value.startswith("/")
            or value.endswith("/")
            or value.endswith(".")
            or "//" in value
            or ".." in value
            or value == "@{"
        ):
            raise ValueError("branch must be a valid git ref name")
        return value

    @field_validator("path_filter", mode="before")
    @classmethod
    def normalize_path_filter(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value

        normalized = value.strip().strip("/")
        return normalized or None

    @field_validator("path_filter")
    @classmethod
    def validate_path_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "\\" in value:
            raise ValueError("path_filter must use forward slashes")
        if "?" in value or "#" in value:
            raise ValueError("path_filter must be a relative repository path")
        if any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("path_filter must be a relative repository path")
        return value


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SourceName
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
    data: list[SourceResponse]
    meta: dict


class SourceSyncData(BaseModel):
    audit_job_id: uuid.UUID
    status: AuditJobStatus
    documents_seen: Optional[int] = None
    documents_created: Optional[int] = None
    versions_created: Optional[int] = None


class SourceSyncResponse(BaseModel):
    data: SourceSyncData
