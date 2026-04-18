from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Secretary AI"
    environment: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    timezone: str = "Europe/London"


@lru_cache
def get_settings() -> Settings:
    return Settings()
