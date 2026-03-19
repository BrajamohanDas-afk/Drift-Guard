from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    
    model_config = ConfigDict(env_file=".env")
    
    # Variable here
    database_url: str
    alembic_database_url: str
    redis_url: str
    secret_key: str
    github_token: str


settings = Settings()
