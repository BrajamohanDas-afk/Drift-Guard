import app.services.ingestion.git_ingestor as git_ingestor_module
from app.services.ingestion.git_ingestor import GitIngestor


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

    captured = {}

    class FakeGithub:
        def __init__(self, token):
            captured["token"] = token

        def get_repo(self, repo_name):
            captured["repo_name"] = repo_name
            return repo

    monkeypatch.setattr(git_ingestor_module, "Github", FakeGithub)

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