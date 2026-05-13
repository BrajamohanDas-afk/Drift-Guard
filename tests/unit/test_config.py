import pytest
from pydantic import ValidationError

from app.config import Settings

BASE_SETTINGS = {
    "database_url": "postgresql+asyncpg://drift:drift@postgres:5432/driftguard",
    "alembic_database_url": "postgresql+psycopg2://drift:drift@postgres:5432/driftguard",
    "redis_url": "redis://:local-dev-redis-password@redis:6379/0",
    "redis_password": "local-dev-redis-password",
    "secret_key": "local-dev-secret-key-replace-before-shared-use",
    "api_key": "dg_local_dev_api_key_replace_before_shared_use",
}


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB fixture: these are pure unit tests.
    yield


def test_settings_accept_local_development_values():
    settings = Settings(_env_file=None, **BASE_SETTINGS)

    assert settings.redis_url == "redis://:local-dev-redis-password@redis:6379/0"
    assert settings.redis_password == "local-dev-redis-password"
    assert settings.github_token == ""


@pytest.mark.parametrize(
    ("field_name", "placeholder"),
    [
        ("secret_key", "your-secret-key-here"),
        ("api_key", "change-me"),
        ("github_token", "your-github-token-here"),
    ],
)
def test_settings_reject_known_placeholder_secrets(field_name, placeholder):
    values = {**BASE_SETTINGS, field_name: placeholder}

    with pytest.raises(ValidationError, match=field_name):
        Settings(_env_file=None, **values)


def test_settings_require_non_empty_api_key_and_secret_key():
    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None, **{**BASE_SETTINGS, "secret_key": ""})

    with pytest.raises(ValidationError, match="api_key"):
        Settings(_env_file=None, **{**BASE_SETTINGS, "api_key": ""})
