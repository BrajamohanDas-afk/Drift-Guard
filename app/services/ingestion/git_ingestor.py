from github import Github
from typing import Optional
from urllib.parse import urlparse
from github import GithubException


class GitIngestor:
    def __init__(
        self,
        repo_url: str,
        token: str,
        branch: str = "main",
        path_filter: Optional[str] = None,
    ):
        self.repo_url = repo_url
        self.token = token
        self.branch = branch
        self.path_filter = path_filter

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

    def _collect_markdown_files(self, repo, path: str) -> list[dict]:
        contents = repo.get_contents(path, ref=self.branch)
        if not isinstance(contents, list):
            contents = [contents]

        files: list[dict] = []

        for item in contents:
            if item.type == "dir":
                files.extend(self._collect_markdown_files(repo, item.path))
                continue

            if item.type == "file" and item.name.lower().endswith(".md"):
                files.append(
                    {
                        "filename": item.name,
                        "path": item.path,
                        "content": item.decoded_content.decode("utf-8"),
                    }
                )

        return files

    def fetch_markdown_files(self) -> list[dict]:
        try:
            github_client = Github(self.token)
            repo = github_client.get_repo(self._normalize_repo_name())
            return self._collect_markdown_files(repo, self.path_filter or "")
        except GithubException as e:
            raise Exception(f"GitHub error: {e.status} {e.data}") from e