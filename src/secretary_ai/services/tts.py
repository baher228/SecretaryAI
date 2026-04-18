from datetime import datetime, timezone
from pathlib import Path

from secretary_ai.core.config import Settings

try:
    import edge_tts
except Exception:  # pragma: no cover - optional dependency
    edge_tts = None  # type: ignore[assignment]


class TTSEngine:
    """Simple TTS adapter. Current default provider: edge-tts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def synthesize(self, text: str, call_id: str) -> tuple[str | None, str]:
        clean_text = (text or "").strip()
        if not clean_text:
            return None, "empty_text"
        if not self.settings.tts_enabled:
            return None, "disabled"

        provider = (self.settings.tts_provider or "").lower().strip()
        if provider != "edge_tts":
            return None, f"unsupported_provider:{provider or 'unknown'}"
        if edge_tts is None:
            return None, "edge_tts_not_installed"

        root = Path(self.settings.telegram_audio_root) / "generated"
        root.mkdir(parents=True, exist_ok=True)
        safe_call = call_id.replace("/", "_").replace("\\", "_")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_path = root / f"{safe_call}-{ts}.mp3"

        try:
            voice_name = self._resolve_voice_name(self.settings.tts_voice)
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=voice_name,
                rate=self.settings.tts_rate,
                volume=self.settings.tts_volume,
            )
            await communicate.save(str(output_path))
            return str(output_path.resolve()), "generated"
        except Exception:
            return None, "generation_failed"

    @staticmethod
    def _resolve_voice_name(configured_voice: str) -> str:
        voice = (configured_voice or "").strip()
        if not voice:
            return "en-US-AriaNeural"
        # Compatibility aliases: allow common Amazon Polly names while using edge-tts backend.
        polly_aliases = {
            "Polly.Joanna": "en-US-JennyNeural",
        }
        return polly_aliases.get(voice, voice)
