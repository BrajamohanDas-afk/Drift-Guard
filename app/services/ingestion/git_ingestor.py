from github import Github
from github import GithubException
from typing import Optional


class GitIngestor:
    def __init__(self, repo_url: str, token: str, branch: str = "main", path_filter: Optional[str] = None):
        self.repo_url = repo_url
        self.token = token
        self.branch = branch
        self.path_filter = path_filter
        
    def fetch_markdown_files(self) -> list[dict]:
        try:
            g = Github(self.token)
            # from "https://github.com/acme/runbooks" → "acme/runbooks"
            repo_name = self.repo_url.replace("https://github.com/", "")
            repo = g.get_repo(repo_name)
            contents = repo.get_contents(self.path_filter or "", ref=self.branch)
            files = []
            for file in contents:
                if file.name.endswith(".md"):
                    files.append({
                        "filename": file.name,
                        "path": file.path,
                        "content": file.decoded_content.decode("utf-8")
                    })
            return files
        except GithubException as e:
            raise Exception(f"GitHub error: {e.status} {e.data}")