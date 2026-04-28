from functools import lru_cache

from pydantic import model_validator
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
    language: str = "ru"

    zai_api_key: str | None = None
    tavily_api_key: str | None = None
    google_maps_api_key: str | None = None
    zai_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    zai_model: str = "glm-4.5-air"
    zai_chat_model: str | None = None
    zai_timeout_seconds: float = 30.0
    agent_max_tokens: int = 160
    agent_history_turns: int = 4
    agent_live_max_tokens: int = 72
    agent_live_history_turns: int = 1
    agent_live_temperature: float = 0.1
    agent_live_template_enabled: bool = True
    agent_live_template_path: str = ".telegram/cache/live_reply_templates.json"
    agent_live_timeout_seconds: float = 1.8
    agent_live_low_quality_reply: str | None = None
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
    assistant_greeting_message: str | None = None

    tts_enabled: bool = True
    tts_provider: str = "edge_tts"
    tts_voice: str | None = None
    tts_rate: str = "+0%"
    tts_volume: str = "+0%"

    stt_enabled: bool = True
    stt_provider: str = "faster_whisper"
    stt_model: str | None = None
    stt_language: str | None = None
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_min_chars: int = 4
    stt_recent_only: bool = True
    stt_tail_seconds: float = 2.0
    stt_min_new_bytes: int = 1200
    stt_repeat_similarity_threshold: float = 0.9
    stt_transcribe_timeout_seconds: float = 8.0
    stt_prewarm_on_startup: bool = True
    telegram_live_poll_seconds: float = 0.3
    telegram_live_tts_cooldown_seconds: float = 0.3
    telegram_live_debug: bool = True
    telegram_live_debug_log_path: str = ".telegram/logs/live_debug.jsonl"
    telegram_live_log_transcript_preview_chars: int = 120
    telegram_stream_play_timeout_seconds: float = 2.5
    template_reply_cooldown_seconds: float = 6.0

    calendar_enabled: bool = False
    calendar_timezone: str = "Europe/London"
    calendar_id: str | None = None
    calendar_service_account_json: str | None = None
    calendar_cache_path: str = ".telegram/cache/calendar_events.json"
    calendar_queue_path: str = ".telegram/cache/calendar_queue.json"
    calendar_worker_enabled: bool = True
    calendar_worker_poll_seconds: float = 2.0
    calendar_worker_batch_size: int = 4
    calendar_smart_model: str | None = None
    calendar_planner_max_tokens: int = 140
    calendar_refresh_interval_seconds: float = 300.0

    reminder_enabled: bool = True
    reminder_target_user: str | None = None
    reminder_lead_minutes: int = 60
    reminder_scan_horizon_hours: int = 48
    reminder_state_path: str = ".telegram/cache/reminder_state.json"

    audio_cleanup_enabled: bool = True
    audio_cleanup_interval_seconds: float = 600.0
    audio_cleanup_max_age_hours: float = 24.0
    audio_cleanup_keep_recent_files: int = 60

    # Gemini Live (audio-to-audio voice loop).
    # Enabled by default; falls back to STT/AI/TTS when the API key is absent.
    gemini_api_key: str | None = None
    gemini_live_model: str = "gemini-3.1-flash-live-preview"
    gemini_live_voice: str = "Zephyr"
    gemini_live_enabled: bool = True

    @model_validator(mode="after")
    def _apply_language_defaults(self) -> "Settings":
        """Fill language-dependent fields that were not explicitly set."""
        from secretary_ai.core.locales import (
            DEFAULT_STT_MODEL,
            DEFAULT_TTS_VOICE,
            GREETING_MESSAGE,
            LOW_QUALITY_REPLY,
            t,
        )

        lang = self.language
        if self.tts_voice is None:
            self.tts_voice = t(DEFAULT_TTS_VOICE, lang)
        if self.stt_model is None:
            self.stt_model = t(DEFAULT_STT_MODEL, lang)
        if self.stt_language is None:
            self.stt_language = lang
        if self.assistant_greeting_message is None:
            self.assistant_greeting_message = t(GREETING_MESSAGE, lang)
        if self.agent_live_low_quality_reply is None:
            self.agent_live_low_quality_reply = t(LOW_QUALITY_REPLY, lang)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
