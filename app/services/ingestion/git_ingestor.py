import time
from dataclasses import dataclass
from urllib.parse import urlparse

from github import Github, GithubException

DEFAULT_MAX_MARKDOWN_FILES = 500
DEFAULT_MAX_FILE_BYTES = 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0


class GitIngestorBudgetExceeded(ValueError):
    pass


@dataclass
class _CollectionBudget:
    max_markdown_files: int
    max_file_bytes: int
    max_total_bytes: int
    deadline: float
    files_collected: int = 0
    total_bytes: int = 0

    def check_timeout(self, *, path: str) -> None:
        if time.monotonic() > self.deadline:
            raise GitIngestorBudgetExceeded(
                "Git sync timed out while scanning "
                f"{path!r} after collecting {self.files_collected} files"
            )

    def add_markdown_file(self, *, path: str, content: bytes) -> str:
        file_bytes = len(content)
        if file_bytes > self.max_file_bytes:
            raise GitIngestorBudgetExceeded(
                f"Git sync exceeded max_file_bytes={self.max_file_bytes} "
                f"for {path!r}"
            )
        if self.files_collected >= self.max_markdown_files:
            raise GitIngestorBudgetExceeded(
                "Git sync exceeded "
                f"max_markdown_files={self.max_markdown_files}"
            )
        if self.total_bytes + file_bytes > self.max_total_bytes:
            raise GitIngestorBudgetExceeded(
                "Git sync exceeded "
                f"max_total_bytes={self.max_total_bytes} "
                f"after collecting {self.files_collected} files"
            )

        self.files_collected += 1
        self.total_bytes += file_bytes
        return content.decode("utf-8")


class GitIngestor:
    def __init__(
        self,
        repo_url: str,
        token: str,
        branch: str = "main",
        path_filter: str | None = None,
        max_markdown_files: int = DEFAULT_MAX_MARKDOWN_FILES,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.repo_url = repo_url
        self.token = token
        self.branch = branch
        self.path_filter = path_filter
        self.max_markdown_files = max_markdown_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.timeout_seconds = timeout_seconds

    def _normalize_repo_name(self) -> str:
        repo_url = self.repo_url.strip()

        if repo_url.startswith("git@github.com:"):
            repo_name = repo_url.removeprefix("git@github.com:")
        else:
            parsed = urlparse(repo_url)
            if parsed.scheme and parsed.netloc:
                if parsed.netloc != "github.com":
                    raise ValueError("repo_url must point to github.com")
                repo_name = parsed.path
            else:
                repo_name = repo_url

        repo_name = repo_name.strip("/")
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        if repo_name.count("/") != 1:
            raise ValueError("repo_url must resolve to owner/repo")

        return repo_name

    def _collection_budget(self) -> _CollectionBudget:
        return _CollectionBudget(
            max_markdown_files=self.max_markdown_files,
            max_file_bytes=self.max_file_bytes,
            max_total_bytes=self.max_total_bytes,
            deadline=time.monotonic() + self.timeout_seconds,
        )

    def _collect_markdown_files(
        self,
        repo,
        path: str,
        budget: _CollectionBudget,
    ) -> list[dict]:
        budget.check_timeout(path=path)
        contents = repo.get_contents(path, ref=self.branch)
        budget.check_timeout(path=path)

        if not isinstance(contents, list):
            contents = [contents]

        files: list[dict] = []

        for item in contents:
            if item.type == "dir":
                files.extend(self._collect_markdown_files(repo, item.path, budget))
                continue

            if item.type == "file" and item.name.lower().endswith(".md"):
                content = budget.add_markdown_file(
                    path=item.path,
                    content=item.decoded_content,
                )
                files.append(
                    {
                        "filename": item.name,
                        "path": item.path,
                        "content": content,
                    }
                )

        return files

    def fetch_markdown_files(self) -> list[dict]:
        try:
            github_client = Github(self.token)
            repo = github_client.get_repo(self._normalize_repo_name())
            return self._collect_markdown_files(
                repo,
                self.path_filter or "",
                self._collection_budget(),
            )
        except GithubException as exc:
            raise Exception(f"GitHub error: {exc.status} {exc.data}") from exc
