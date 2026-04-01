import pytest
from github import GithubException

import app.services.evidence.github_collector as github_collector_module
from app.services.evidence.github_collector import GitHubEvidenceCollector


class FakeContent:
    def __init__(self, sha: str = "abc123", size: int = 42, html_url: str = "https://github.com/acme/runbooks/blob/main/docs/runbook.md"):
        self.sha = sha
        self.size = size
        self.html_url = html_url


class FakeRepo:
    def __init__(self, should_fail: bool = False, fail_status: int = 404):
        self.should_fail = should_fail
        self.fail_status = fail_status

    def get_contents(self, path: str, ref: str):
        if self.should_fail:
            raise GithubException(
                status=self.fail_status,
                data={"message": "failure"},
                headers=None,
            )
        return FakeContent()


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB reset fixture: these are pure unit tests.
    yield


def test_collect_file_success(monkeypatch):
    captured = {}

    class FakeGithub:
        def __init__(self, token: str):
            captured["token"] = token

        def get_repo(self, repo_name: str):
            captured["repo_name"] = repo_name
            return FakeRepo()

    monkeypatch.setattr(github_collector_module, "Github", FakeGithub)

    collector = GitHubEvidenceCollector(token="test-token")
    result = collector.collect_file(
        repo_url="https://github.com/acme/runbooks.git/",
        path="docs/runbook.md",
        branch="main",
    )

    assert captured["token"] == "test-token"
    assert captured["repo_name"] == "acme/runbooks"
    assert result.repo == "acme/runbooks"
    assert result.branch == "main"
    assert result.path == "docs/runbook.md"
    assert result.exists is True
    assert result.owner == "acme"
    assert result.sha == "abc123"
    assert result.size == 42
    assert result.error is None
    assert result.checked_at.tzinfo is not None
    assert result.checked_at.utcoffset() is not None


def test_collect_file_404_not_found(monkeypatch):
    class FakeGithub:
        def __init__(self, token: str):
            self.token = token

        def get_repo(self, repo_name: str):
            return FakeRepo(should_fail=True, fail_status=404)

    monkeypatch.setattr(github_collector_module, "Github", FakeGithub)

    collector = GitHubEvidenceCollector(token="test-token")
    result = collector.collect_file(
        repo_url="https://github.com/acme/runbooks",
        path="missing.md",
        branch="main",
    )

    assert result.exists is False
    assert result.error is None
    assert result.owner == "acme"
    assert result.repo == "acme/runbooks"


def test_collect_file_non_404_github_error(monkeypatch):
    class FakeGithub:
        def __init__(self, token: str):
            self.token = token

        def get_repo(self, repo_name: str):
            return FakeRepo(should_fail=True, fail_status=403)

    monkeypatch.setattr(github_collector_module, "Github", FakeGithub)

    collector = GitHubEvidenceCollector(token="test-token")
    result = collector.collect_file(
        repo_url="https://github.com/acme/runbooks",
        path="docs/runbook.md",
        branch="main",
    )

    assert result.exists is False
    assert result.error is not None
    assert "GitHub error: 403" in result.error


def test_collect_file_invalid_repo_url():
    collector = GitHubEvidenceCollector(token="test-token")
    result = collector.collect_file(
        repo_url="https://gitlab.com/acme/runbooks",
        path="docs/runbook.md",
        branch="main",
    )

    assert result.exists is False
    assert result.error == "repo_url must point to github.com"
