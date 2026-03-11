from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Variable here
    database_url: str
    redis_url: str
    secret_key: str

    class Config:
        env_file = ".env"


settings = Settings()
