from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Secretary AI"
    environment: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    timezone: str = "Europe/London"

    zai_api_key: str | None = None
    zai_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    zai_model: str = "glm-4.5-air"
    zai_chat_model: str | None = None
    zai_timeout_seconds: float = 30.0
    agent_max_tokens: int = 160
    agent_history_turns: int = 4
    chat_max_tokens: int = 64
    chat_temperature: float = 0.15

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session_path: str = ".telegram/secretary"
    telegram_auto_answer_inbound: bool = True
    telegram_auto_start_live_agent: bool = True
    telegram_auto_start_live_speak_response: bool = True
    telegram_auto_start_scan_seconds: float = 2.0
    telegram_audio_root: str = ".telegram/audio"
    assistant_auto_greet_on_connect: bool = True
    assistant_greeting_message: str = "Hello, this is your AI secretary. How can I help you today?"

    tts_enabled: bool = True
    tts_provider: str = "edge_tts"
    tts_voice: str = "en-GB-SoniaNeural"
    tts_rate: str = "+0%"
    tts_volume: str = "+0%"

    stt_enabled: bool = True
    stt_provider: str = "faster_whisper"
    stt_model: str = "small.en"
    stt_language: str = "en"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_min_chars: int = 6
    stt_recent_only: bool = True
    stt_tail_seconds: float = 2.0
    stt_min_new_bytes: int = 4000
    telegram_live_poll_seconds: float = 0.6
    telegram_live_tts_cooldown_seconds: float = 2.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
