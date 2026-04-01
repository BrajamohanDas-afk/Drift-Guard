from pydantic import ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    database_url: str
    alembic_database_url: str
    redis_url: str
    secret_key: str
    github_token: str
    sql_echo: bool = False
    api_key: str
    pagerduty_api_token: str | None = None
    kubernetes_api_url: str | None = None
    kubernetes_bearer_token: str | None = None
    kubernetes_verify_ssl: bool = True
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
