from pydantic import ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    database_url: str
    alembic_database_url: str
    redis_url: str
    secret_key: str
    github_token: str
    sql_echo: bool = False
    api_key: str

settings = Settings()