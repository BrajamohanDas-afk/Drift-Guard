import pytest

import app.services.ingestion.git_ingestor as git_ingestor_module
from app.services.ingestion.git_ingestor import GitIngestor, GitIngestorBudgetExceeded


class FakeContent:
    def __init__(self, name, path, content_type, content=""):
        self.name = name
        self.path = path
        self.type = content_type
        self.decoded_content = content.encode("utf-8")


class FakeRepo:
    def __init__(self, contents_by_path):
        self.contents_by_path = contents_by_path
        self.calls = []

    def get_contents(self, path, ref):
        self.calls.append((path, ref))
        return self.contents_by_path[path]


def _patch_github(monkeypatch, repo):
    captured = {}

    class FakeGithub:
        def __init__(self, token):
            captured["token"] = token

        def get_repo(self, repo_name):
            captured["repo_name"] = repo_name
            return repo

    monkeypatch.setattr(git_ingestor_module, "Github", FakeGithub)
    return captured


def test_fetch_markdown_files_recurses_and_normalizes_repo_url(monkeypatch):
    repo = FakeRepo(
        {
            "docs/runbooks": [
                FakeContent(
                    name="root.md",
                    path="docs/runbooks/root.md",
                    content_type="file",
                    content="# Root",
                ),
                FakeContent(
                    name="services",
                    path="docs/runbooks/services",
                    content_type="dir",
                ),
                FakeContent(
                    name="notes.txt",
                    path="docs/runbooks/notes.txt",
                    content_type="file",
                    content="ignore me",
                ),
            ],
            "docs/runbooks/services": [
                FakeContent(
                    name="service-a.md",
                    path="docs/runbooks/services/service-a.md",
                    content_type="file",
                    content="# Service A",
                ),
            ],
        }
    )

    captured = _patch_github(monkeypatch, repo)

    ingestor = GitIngestor(
        repo_url="https://github.com/acme/runbooks.git/",
        token="test-token",
        branch="main",
        path_filter="docs/runbooks",
    )

    files = ingestor.fetch_markdown_files()

    assert captured["token"] == "test-token"
    assert captured["repo_name"] == "acme/runbooks"
    assert repo.calls == [
        ("docs/runbooks", "main"),
        ("docs/runbooks/services", "main"),
    ]
    assert [file["path"] for file in files] == [
        "docs/runbooks/root.md",
        "docs/runbooks/services/service-a.md",
    ]
    assert [file["content"] for file in files] == [
        "# Root",
        "# Service A",
    ]


def test_fetch_markdown_files_enforces_file_count_budget(monkeypatch):
    repo = FakeRepo(
        {
            "": [
                FakeContent("a.md", "a.md", "file", "# A"),
                FakeContent("b.md", "b.md", "file", "# B"),
            ]
        }
    )
    _patch_github(monkeypatch, repo)

    ingestor = GitIngestor(
        repo_url="https://github.com/acme/runbooks",
        token="test-token",
        max_markdown_files=1,
    )

    with pytest.raises(
        GitIngestorBudgetExceeded,
        match="max_markdown_files=1",
    ):
        ingestor.fetch_markdown_files()


def test_fetch_markdown_files_enforces_file_size_budget(monkeypatch):
    repo = FakeRepo(
        {
            "": [
                FakeContent("large.md", "large.md", "file", "large"),
            ]
        }
    )
    _patch_github(monkeypatch, repo)

    ingestor = GitIngestor(
        repo_url="https://github.com/acme/runbooks",
        token="test-token",
        max_file_bytes=4,
    )

    with pytest.raises(
        GitIngestorBudgetExceeded,
        match="max_file_bytes=4",
    ):
        ingestor.fetch_markdown_files()


def test_fetch_markdown_files_enforces_total_size_budget(monkeypatch):
    repo = FakeRepo(
        {
            "": [
                FakeContent("a.md", "a.md", "file", "abc"),
                FakeContent("b.md", "b.md", "file", "def"),
            ]
        }
    )
    _patch_github(monkeypatch, repo)

    ingestor = GitIngestor(
        repo_url="https://github.com/acme/runbooks",
        token="test-token",
        max_total_bytes=5,
    )

    with pytest.raises(
        GitIngestorBudgetExceeded,
        match="max_total_bytes=5 after collecting 1 files",
    ):
        ingestor.fetch_markdown_files()


def test_fetch_markdown_files_enforces_timeout_budget(monkeypatch):
    repo = FakeRepo({"": []})
    _patch_github(monkeypatch, repo)
    times = iter([0.0, 2.0])
    monkeypatch.setattr(
        git_ingestor_module.time,
        "monotonic",
        lambda: next(times),
    )

    ingestor = GitIngestor(
        repo_url="https://github.com/acme/runbooks",
        token="test-token",
        timeout_seconds=1,
    )

    with pytest.raises(GitIngestorBudgetExceeded, match="timed out"):
        ingestor.fetch_markdown_files()
