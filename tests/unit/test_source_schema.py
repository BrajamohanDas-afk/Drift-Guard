import pytest
from pydantic import ValidationError

from app.schemas.source import SourceCreate


def _source_payload(**config_overrides):
    config = {
        "repo_url": "https://github.com/acme/runbooks",
        "branch": "main",
        "path_filter": "docs",
    }
    config.update(config_overrides)
    return {
        "name": "Runbooks",
        "type": "git",
        "config": config,
    }


def test_source_create_normalizes_branch_and_path_filter():
    source = SourceCreate.model_validate(
        _source_payload(
            repo_url=" https://github.com/acme/runbooks.git/ ",
            branch=" release/2026.05 ",
            path_filter=" /docs/runbooks/ ",
        )
    )

    assert source.name == "Runbooks"
    assert source.config.repo_url == "https://github.com/acme/runbooks.git/"
    assert source.config.branch == "release/2026.05"
    assert source.config.path_filter == "docs/runbooks"


def test_source_create_allows_github_ssh_and_owner_repo_forms():
    ssh_source = SourceCreate.model_validate(
        _source_payload(repo_url="git@github.com:acme/runbooks.git")
    )
    short_source = SourceCreate.model_validate(
        _source_payload(repo_url="acme/runbooks")
    )

    assert ssh_source.config.repo_url == "git@github.com:acme/runbooks.git"
    assert short_source.config.repo_url == "acme/runbooks"


def test_source_create_rejects_unknown_config_fields():
    payload = _source_payload(token="secret")

    with pytest.raises(ValidationError):
        SourceCreate.model_validate(payload)


def test_source_create_rejects_non_github_repo_url():
    with pytest.raises(ValidationError, match="repo_url must point to github.com"):
        SourceCreate.model_validate(
            _source_payload(repo_url="https://gitlab.com/acme/runbooks")
        )


def test_source_create_rejects_malformed_repo_url():
    with pytest.raises(ValidationError, match="repo_url must resolve to owner/repo"):
        SourceCreate.model_validate(_source_payload(repo_url="https://github.com/acme"))


def test_source_create_rejects_invalid_branch():
    with pytest.raises(ValidationError, match="branch must be a valid git ref name"):
        SourceCreate.model_validate(_source_payload(branch="../main"))


def test_source_create_rejects_unsafe_path_filter():
    with pytest.raises(
        ValidationError,
        match="path_filter must be a relative repository path",
    ):
        SourceCreate.model_validate(_source_payload(path_filter="docs/../secrets"))
