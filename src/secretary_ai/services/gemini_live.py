"""Gemini Live audio-to-audio bridge for Telegram call voice loop.

Connects to Google's Gemini 3.1 Flash Live API and streams call audio
(from the py-tgcalls recording file) directly to Gemini, receiving
spoken audio responses back.  This replaces the STT -> Z.AI -> TTS
pipeline with a single native audio-to-audio model.
"""

from __future__ import annotations

import asyncio
import struct
import wave
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings

try:
    from google import genai
    from google.genai import types

    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False


SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
SEND_AUDIO_MIME = f"audio/pcm;rate={SEND_SAMPLE_RATE}"
RECEIVE_AUDIO_MIME = f"audio/pcm;rate={RECEIVE_SAMPLE_RATE}"

WAV_HEADER_SIZE = 44


def _resample_pcm16(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Resample 16-bit mono PCM by nearest-neighbour selection."""
    if src_rate == dst_rate:
        return data
    aligned = len(data) // 2 * 2
    src_samples = struct.unpack(f"<{aligned // 2}h", data[:aligned])
    ratio = src_rate / dst_rate
    dst_count = int(len(src_samples) / ratio)
    dst_samples = [src_samples[min(int(i * ratio), len(src_samples) - 1)] for i in range(dst_count)]
    return struct.pack(f"<{len(dst_samples)}h", *dst_samples)


def _write_wav(path: Path, pcm_data: bytes, sample_rate: int) -> None:
    """Write raw 16-bit mono PCM bytes to a WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


class GeminiLiveSession:
    """Manages a single Gemini Live session for one Telegram call."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audio_out_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.transcript_in: list[str] = []
        self.transcript_out: list[str] = []
        self._running = False

    @staticmethod
    def available() -> bool:
        return _GENAI_AVAILABLE

    def _build_client(self) -> Any:
        return genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=self.settings.gemini_api_key,
        )

    def _live_config(self) -> Any:
        system_prompt = (
            "You are a professional AI phone secretary. "
            "You answer calls on behalf of your employer. "
            "Be concise, warm, and helpful. "
            "Keep each spoken response to 1-2 short sentences. "
            "If someone wants to schedule a meeting, ask for date and time. "
            "If unsure, offer to take a message and pass it along."
        )
        return types.LiveConnectConfig(
            responseModalities=[types.Modality.AUDIO],
            systemInstruction=system_prompt,
            speechConfig=types.SpeechConfig(
                voiceConfig=types.VoiceConfig(
                    prebuiltVoiceConfig=types.PrebuiltVoiceConfig(
                        voiceName=self.settings.gemini_live_voice,
                    )
                )
            ),
            inputAudioTranscription=types.AudioTranscriptionConfig(),
            outputAudioTranscription=types.AudioTranscriptionConfig(),
            contextWindowCompression=types.ContextWindowCompressionConfig(
                triggerTokens=100_000,
                slidingWindow=types.SlidingWindow(targetTokens=50_000),
            ),
        )

    async def run(
        self,
        recording_path: Path,
        audio_out_callback: Any,
        stop_check: Any,
        debug_log: Any,
    ) -> None:
        """Main entry point: bridges call audio <-> Gemini Live.

        Parameters
        ----------
        recording_path:
            WAV file being written to by py-tgcalls (grows over time).
        audio_out_callback:
            ``async def cb(wav_path: str) -> dict`` that plays a WAV file
            into the Telegram call.
        stop_check:
            ``def() -> bool`` returns True when the loop should stop.
        debug_log:
            ``def(call_id, event, payload)`` for structured debug logging.
        """
        if not _GENAI_AVAILABLE:
            debug_log("gemini_live_unavailable", {"reason": "google-genai not installed"})
            return
        if not self.settings.gemini_api_key:
            debug_log("gemini_live_unavailable", {"reason": "GEMINI_API_KEY not set"})
            return

        client = self._build_client()
        self._running = True

        try:
            async with client.aio.live.connect(
                model=self.settings.gemini_live_model,
                config=self._live_config(),
            ) as session:
                debug_log("gemini_live_connected", {"model": self.settings.gemini_live_model})
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(
                        self._send_audio_loop(session, recording_path, stop_check, debug_log)
                    )
                    tg.create_task(
                        self._receive_audio_loop(session, stop_check, debug_log)
                    )
                    tg.create_task(
                        self._play_audio_loop(
                            recording_path.parent,
                            recording_path.stem,
                            audio_out_callback,
                            stop_check,
                            debug_log,
                        )
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            debug_log(
                "gemini_live_session_error",
                {"error": exc.__class__.__name__, "detail": str(exc)[:300]},
            )
        finally:
            self._running = False

    async def _send_audio_loop(
        self,
        session: Any,
        recording_path: Path,
        stop_check: Any,
        debug_log: Any,
    ) -> None:
        """Read new audio from the recording WAV file and send to Gemini."""
        read_offset = 0
        src_rate: int | None = None
        chunks_sent = 0

        while not stop_check():
            if not recording_path.exists():
                await asyncio.sleep(0.3)
                continue

            file_size = recording_path.stat().st_size
            if file_size <= WAV_HEADER_SIZE:
                await asyncio.sleep(0.2)
                continue

            if src_rate is None:
                try:
                    with wave.open(str(recording_path), "rb") as wf:
                        src_rate = wf.getframerate()
                        read_offset = WAV_HEADER_SIZE
                    debug_log("gemini_live_wav_header", {"src_rate": src_rate})
                except Exception:
                    await asyncio.sleep(0.3)
                    continue

            readable = file_size - read_offset
            if readable < 3200:
                await asyncio.sleep(0.15)
                continue

            try:
                raw = await asyncio.to_thread(self._read_bytes, recording_path, read_offset, readable)
            except Exception:
                await asyncio.sleep(0.2)
                continue

            read_offset += len(raw)

            pcm_16k = _resample_pcm16(raw, src_rate, SEND_SAMPLE_RATE)
            if not pcm_16k:
                continue

            try:
                await session.send_realtime_input(
                    audio=types.Blob(data=pcm_16k, mimeType=SEND_AUDIO_MIME),
                )
                chunks_sent += 1
                if chunks_sent == 1 or chunks_sent % 50 == 0:
                    debug_log(
                        "gemini_live_audio_sent",
                        {"chunks": chunks_sent, "offset": read_offset},
                    )
            except Exception as exc:
                debug_log(
                    "gemini_live_send_error",
                    {"error": exc.__class__.__name__, "detail": str(exc)[:200]},
                )
                await asyncio.sleep(0.5)

            await asyncio.sleep(0.1)

    async def _receive_audio_loop(
        self,
        session: Any,
        stop_check: Any,
        debug_log: Any,
    ) -> None:
        """Receive audio/text responses from Gemini and queue them."""
        turns_received = 0

        while not stop_check():
            try:
                async for response in session.receive():
                    if stop_check():
                        return

                    server_content = getattr(response, "server_content", None)

                    if getattr(server_content, "interrupted", False):
                        while not self.audio_out_queue.empty():
                            self.audio_out_queue.get_nowait()
                        debug_log("gemini_live_interrupted", {})

                    audio_chunks = self._extract_audio(response, server_content)
                    for chunk in audio_chunks:
                        self.audio_out_queue.put_nowait(chunk)

                    input_tx = getattr(server_content, "input_transcription", None)
                    if input_tx and getattr(input_tx, "text", None):
                        self.transcript_in.append(input_tx.text)
                        debug_log(
                            "gemini_live_input_transcript",
                            {"text": input_tx.text[:200]},
                        )

                    output_tx = getattr(server_content, "output_transcription", None)
                    if output_tx and getattr(output_tx, "text", None):
                        self.transcript_out.append(output_tx.text)
                        debug_log(
                            "gemini_live_output_transcript",
                            {"text": output_tx.text[:200]},
                        )

                    if getattr(server_content, "turn_complete", False):
                        turns_received += 1
                        debug_log(
                            "gemini_live_turn_complete",
                            {"turns": turns_received},
                        )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                debug_log(
                    "gemini_live_receive_error",
                    {"error": exc.__class__.__name__, "detail": str(exc)[:200]},
                )
                if stop_check():
                    return
                await asyncio.sleep(0.5)

    async def _play_audio_loop(
        self,
        audio_dir: Path,
        call_prefix: str,
        audio_out_callback: Any,
        stop_check: Any,
        debug_log: Any,
    ) -> None:
        """Drain received audio chunks, write WAV, and play into the call."""
        response_idx = 0
        audio_dir.mkdir(parents=True, exist_ok=True)

        while not stop_check():
            if self.audio_out_queue.empty():
                await asyncio.sleep(0.05)
                continue

            collected: list[bytes] = []
            while not self.audio_out_queue.empty():
                collected.append(self.audio_out_queue.get_nowait())

            if not collected:
                continue

            pcm_data = b"".join(collected)
            target_rate = 48000
            pcm_48k = _resample_pcm16(pcm_data, RECEIVE_SAMPLE_RATE, target_rate)

            wav_path = audio_dir / f"gemini_{call_prefix}_{response_idx}.wav"
            try:
                await asyncio.to_thread(_write_wav, wav_path, pcm_48k, target_rate)
            except Exception as exc:
                debug_log(
                    "gemini_live_wav_write_error",
                    {"error": exc.__class__.__name__, "path": str(wav_path)},
                )
                continue

            try:
                result = await audio_out_callback(str(wav_path))
                status = result.get("status") if isinstance(result, dict) else str(result)
                debug_log(
                    "gemini_live_audio_played",
                    {"idx": response_idx, "bytes": len(pcm_data), "status": status},
                )
            except Exception as exc:
                debug_log(
                    "gemini_live_play_error",
                    {"error": exc.__class__.__name__, "detail": str(exc)[:200]},
                )

            response_idx += 1

    @staticmethod
    def _extract_audio(response: Any, server_content: Any) -> list[bytes]:
        chunks: list[bytes] = []
        model_turn = getattr(server_content, "model_turn", None)
        for part in getattr(model_turn, "parts", []) or []:
            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None)
            if isinstance(data, bytes):
                chunks.append(data)
        if chunks:
            return chunks
        data = getattr(response, "data", None)
        return [data] if isinstance(data, bytes) else []

    @staticmethod
    def _read_bytes(path: Path, offset: int, count: int) -> bytes:
        with open(path, "rb") as fh:
            fh.seek(offset)
            return fh.read(count)
