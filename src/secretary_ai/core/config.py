from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Secretary AI"
    environment: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    timezone: str = "Europe/London"

    zai_api_key: str | None = None
    zai_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    zai_model: str = "glm-5.1"
    zai_timeout_seconds: float = 30.0

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session_path: str = ".telegram/secretary"
    telegram_auto_answer_inbound: bool = True
    telegram_audio_root: str = ".telegram/audio"


@lru_cache
def get_settings() -> Settings:
    return Settings()
