import asyncio
import shutil
from contextlib import suppress
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
        self._ffmpeg_path = shutil.which("ffmpeg")

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

        temp_clip: Path | None = None
        source_path = path
        try:
            if self.settings.stt_recent_only:
                temp_clip = await self._extract_recent_clip(path)
                if temp_clip is not None:
                    source_path = temp_clip

            model = await asyncio.to_thread(self._ensure_model)
            text = await asyncio.to_thread(self._transcribe_with_model, model, source_path)
            text = " ".join(text.split())
            if not text:
                return "", "no_speech"
            return text, "ok"
        except Exception as exc:
            return "", f"transcription_error:{exc.__class__.__name__}"
        finally:
            if temp_clip is not None:
                with suppress(Exception):
                    temp_clip.unlink(missing_ok=True)

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

    async def _extract_recent_clip(self, source_path: Path) -> Path | None:
        if self._ffmpeg_path is None:
            return None
        tail_seconds = max(1.5, float(self.settings.stt_tail_seconds))
        chunks_root = Path(self.settings.telegram_audio_root) / "chunks"
        chunks_root.mkdir(parents=True, exist_ok=True)
        output_path = chunks_root / f"{source_path.stem}-tail.wav"
        cmd = [
            self._ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-sseof",
            f"-{tail_seconds:.2f}",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=8.0)
        except asyncio.TimeoutError:
            with suppress(Exception):
                proc.kill()
            return None
        if proc.returncode != 0:
            return None
        if not output_path.exists() or output_path.stat().st_size <= 0:
            return None
        return output_path
