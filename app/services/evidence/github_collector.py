from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from github import Github, GithubException
from pydantic import BaseModel, Field

from app.config import settings


class GitHubFileEvidence(BaseModel):
    repo: str
    branch: str
    path: str
    exists: bool
    owner: Optional[str] = None
    sha: Optional[str] = None
    size: Optional[int] = None
    html_url: Optional[str] = None
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GitHubEvidenceCollector:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.github_token

    def _normalize_repo_name(self, repo_url: str) -> str:
        candidate = repo_url.strip()

        if candidate.startswith("git@github.com:"):
            repo_name = candidate.removeprefix("git@github.com:")
        else:
            parsed = urlparse(candidate)
            if parsed.scheme and parsed.netloc:
                if parsed.netloc != "github.com":
                    raise ValueError("repo_url must point to github.com")
                repo_name = parsed.path
            else:
                repo_name = candidate

        repo_name = repo_name.strip("/")
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        if repo_name.count("/") != 1:
            raise ValueError("repo_url must resolve to owner/repo")

        return repo_name

    def collect_file(
        self,
        *,
        repo_url: str,
        path: str,
        branch: str = "main",
    ) -> GitHubFileEvidence:
        checked_at = datetime.now(timezone.utc)

        try:
            repo_name = self._normalize_repo_name(repo_url)
        except ValueError as exc:
            return GitHubFileEvidence(
                repo=repo_url.strip(),
                branch=branch,
                path=path,
                exists=False,
                error=str(exc),
                checked_at=checked_at,
            )

        owner = repo_name.split("/")[0]

        try:
            github_client = Github(self.token)
            repo = github_client.get_repo(repo_name)
            content = repo.get_contents(path, ref=branch)

            if isinstance(content, list):
                return GitHubFileEvidence(
                    repo=repo_name,
                    branch=branch,
                    path=path,
                    exists=False,
                    owner=owner,
                    error="Path points to a directory, expected a file",
                    checked_at=checked_at,
                )

            return GitHubFileEvidence(
                repo=repo_name,
                branch=branch,
                path=path,
                exists=True,
                owner=owner,
                sha=getattr(content, "sha", None),
                size=getattr(content, "size", None),
                html_url=getattr(content, "html_url", None),
                error=None,
                checked_at=checked_at,
            )
        except GithubException as exc:
            if exc.status == 404:
                return GitHubFileEvidence(
                    repo=repo_name,
                    branch=branch,
                    path=path,
                    exists=False,
                    owner=owner,
                    error=None,
                    checked_at=checked_at,
                )

            return GitHubFileEvidence(
                repo=repo_name,
                branch=branch,
                path=path,
                exists=False,
                owner=owner,
                error=f"GitHub error: {exc.status} {exc.data}",
                checked_at=checked_at,
            )
        except Exception as exc:
            return GitHubFileEvidence(
                repo=repo_name,
                branch=branch,
                path=path,
                exists=False,
                owner=owner,
                error=str(exc),
                checked_at=checked_at,
            )
