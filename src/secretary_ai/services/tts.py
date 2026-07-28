"""TTS engine supporting Edge TTS and Silero (Russian-native) providers."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings

logger = logging.getLogger(__name__)

try:
    import edge_tts
except Exception:  # pragma: no cover - optional dependency
    edge_tts = None  # type: ignore[assignment]

# Silero is loaded lazily on first use to avoid heavy torch import at startup.
_silero_model: Any = None
_silero_load_error: RuntimeError | None = None
_silero_lock = asyncio.Lock()


async def _get_silero_model(settings: Settings) -> Any:
    """Load and cache the Silero TTS model (thread-safe, lazy)."""
    global _silero_model, _silero_load_error  # noqa: PLW0603
    if _silero_model is not None:
        return _silero_model
    if _silero_load_error is not None:
        raise _silero_load_error

    async with _silero_lock:
        if _silero_model is not None:
            return _silero_model
        if _silero_load_error is not None:
            raise _silero_load_error

        try:
            model = await asyncio.to_thread(_load_silero_sync, settings)
        except Exception as exc:
            _silero_load_error = RuntimeError("Silero model failed to load")
            raise _silero_load_error from exc
        _silero_model = model
        return model


def _load_silero_sync(settings: Settings) -> Any:
    """Synchronous Silero model load via pip package — runs in executor."""
    try:
        import torch  # noqa: F811
        from silero import silero_tts
    except ImportError as exc:
        raise RuntimeError(
            "silero and torch are required: pip install silero torch"
        ) from exc

    model_id = settings.tts_silero_model_id
    language = "ru" if "ru" in model_id else "en"

    model, _ = silero_tts(language=language, speaker=model_id)
    device = torch.device(settings.tts_silero_device)
    model.to(device)
    logger.info("Silero TTS model loaded: %s on %s", model_id, device)
    return model


class TTSEngine:
    """Multi-provider TTS adapter. Supports edge_tts and silero."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def synthesize(self, text: str, call_id: str) -> tuple[str | None, str]:
        clean_text = (text or "").strip()
        if not clean_text:
            return None, "empty_text"
        if not self.settings.tts_enabled:
            return None, "disabled"

        provider = (self.settings.tts_provider or "").lower().strip()
        if provider == "silero":
            return await self._synthesize_silero(clean_text, call_id)
        if provider == "edge_tts":
            return await self._synthesize_edge(clean_text, call_id)
        return None, f"unsupported_provider:{provider or 'unknown'}"

    # ------------------------------------------------------------------
    # Edge TTS
    # ------------------------------------------------------------------

    async def _synthesize_edge(self, text: str, call_id: str) -> tuple[str | None, str]:
        if edge_tts is None:
            return None, "edge_tts_not_installed"

        output_path = self._output_path(call_id, "mp3")
        try:
            voice_name = self._resolve_edge_voice(
                self.settings.tts_voice,
                self.settings.language,
            )
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_name,
                rate=self.settings.tts_rate,
                volume=self.settings.tts_volume,
            )
            await communicate.save(str(output_path))
            if not output_path.is_file() or output_path.stat().st_size == 0:
                output_path.unlink(missing_ok=True)
                return None, "generation_failed"
            return str(output_path.resolve()), "generated"
        except Exception:
            output_path.unlink(missing_ok=True)
            logger.exception("Edge TTS synthesis failed")
            return None, "generation_failed"

    # ------------------------------------------------------------------
    # Silero TTS (Russian-native, local inference)
    # ------------------------------------------------------------------

    async def _synthesize_silero(self, text: str, call_id: str) -> tuple[str | None, str]:
        try:
            model = await _get_silero_model(self.settings)
        except Exception:
            logger.warning("Silero model unavailable, falling back to Edge TTS")
            return await self._synthesize_edge(text, call_id)

        output_path = self._output_path(call_id, "wav")
        speaker = self.settings.tts_silero_speaker
        sample_rate = self.settings.tts_silero_sample_rate

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: model.save_wav(
                    text=text,
                    speaker=speaker,
                    sample_rate=sample_rate,
                    audio_path=str(output_path),
                ),
            )
            if not output_path.is_file() or output_path.stat().st_size == 0:
                output_path.unlink(missing_ok=True)
                return await self._synthesize_edge(text, call_id)
            return str(output_path.resolve()), "generated"
        except Exception:
            output_path.unlink(missing_ok=True)
            logger.warning("Silero synthesis failed, falling back to Edge TTS")
            return await self._synthesize_edge(text, call_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _output_path(self, call_id: str, ext: str) -> Path:
        root = Path(self.settings.telegram_audio_root) / "generated"
        root.mkdir(parents=True, exist_ok=True)
        safe_call = re.sub(r"[^A-Za-z0-9._-]+", "_", call_id).strip("._")[:80] or "call"
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return root / f"{safe_call}-{ts}.{ext}"

    @staticmethod
    def _resolve_edge_voice(
        configured_voice: str | None,
        language: str | None = None,
    ) -> str:
        voice = (configured_voice or "").strip()
        if not voice:
            return "en-US-AriaNeural"
        polly_aliases = {
            "Polly.Joanna": "en-US-JennyNeural",
        }
        voice = polly_aliases.get(voice, voice)
        language_code = (language or "").split("-", 1)[0].lower()
        defaults = {
            "en": "en-GB-SoniaNeural",
            "ru": "ru-RU-DmitryNeural",
        }
        if language_code in defaults and not voice.lower().startswith(f"{language_code}-"):
            return defaults[language_code]
        return voice

    async def prewarm(self) -> None:
        """Pre-load the TTS model on startup to avoid cold-start latency."""
        provider = (self.settings.tts_provider or "").lower().strip()
        if provider == "silero":
            try:
                await _get_silero_model(self.settings)
                logger.info("Silero TTS model pre-warmed")
            except Exception:
                logger.warning("Silero pre-warm failed; will use Edge TTS fallback")

    @staticmethod
    def available_providers() -> list[str]:
        """Return list of available TTS provider names."""
        providers = ["edge_tts"]
        try:
            import torch  # noqa: F401
            providers.append("silero")
        except ImportError:
            pass
        return providers
