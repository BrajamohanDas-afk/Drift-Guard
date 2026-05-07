from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET_VALUES = {
    "change-me",
    "changeme",
    "your-secret-key-here",
    "your-github-token-here",
    "your-api-key-here",
    "secret",
    "password",
    "replace-me",
    "replace_me",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    alembic_database_url: str
    redis_url: str
    secret_key: str = Field(min_length=32)
    github_token: str = ""
    sql_echo: bool = False
    api_key: str = Field(min_length=16)
    worker_queue_name: str = "drift-guard"
    heavy_endpoint_rate_limit: int = 30
    rate_limit_window_seconds: int = 60
    worker_queue_max_depth: int = 1000
    public_api_docs_enabled: bool = True
    nightly_scan_cron_enabled: bool = True
    nightly_scan_cron_hour_utc: int = 2
    nightly_scan_cron_minute: int = 0
    incidentio_api_token: str | None = None
    incidentio_catalog_type_id: str | None = None
    kubernetes_api_url: str | None = None
    kubernetes_bearer_token: str | None = None
    kubernetes_verify_ssl: bool = True

    @field_validator("secret_key", "api_key", "github_token")
    @classmethod
    def reject_placeholder_secret(cls, value: str, info):
        normalized = value.strip().lower()
        if not normalized and info.field_name == "github_token":
            return value
        if normalized in PLACEHOLDER_SECRET_VALUES:
            raise ValueError(f"{info.field_name} must not use a placeholder value")
        return value


settings = Settings()
