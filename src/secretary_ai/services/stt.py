import asyncio
from pathlib import Path

from secretary_ai.core.config import Settings

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover - optional dependency
    WhisperModel = None  # type: ignore[assignment]


class STTEngine:
    """Simple STT adapter. Current default provider: faster-whisper."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None

    async def transcribe(self, audio_path: str) -> tuple[str, str]:
        path = Path(audio_path)
        if not path.exists():
            return "", "missing_audio_file"
        if path.stat().st_size <= 0:
            return "", "empty_audio_file"
        if not self.settings.stt_enabled:
            return "", "disabled"

        provider = (self.settings.stt_provider or "").strip().lower()
        if provider != "faster_whisper":
            return "", f"unsupported_provider:{provider or 'unknown'}"
        if WhisperModel is None:
            return "", "faster_whisper_not_installed"

        try:
            model = await asyncio.to_thread(self._ensure_model)
            text = await asyncio.to_thread(self._transcribe_with_model, model, path)
            text = " ".join(text.split())
            if not text:
                return "", "no_speech"
            return text, "ok"
        except Exception as exc:
            return "", f"transcription_error:{exc.__class__.__name__}"

    def _ensure_model(self):
        if self._model is None:
            self._model = WhisperModel(
                self.settings.stt_model,
                device=self.settings.stt_device,
                compute_type=self.settings.stt_compute_type,
            )
        return self._model

    def _transcribe_with_model(self, model, path: Path) -> str:
        segments, _ = model.transcribe(
            str(path),
            language=self.settings.stt_language or None,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        collected: list[str] = []
        for segment in segments:
            text = str(getattr(segment, "text", "")).strip()
            if text:
                collected.append(text)
        return " ".join(collected).strip()
