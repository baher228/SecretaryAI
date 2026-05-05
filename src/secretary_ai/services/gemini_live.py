"""Gemini Live audio-to-audio bridge for Telegram call voice loop.

Connects to Google's Gemini 3.1 Flash Live API and streams call audio
(from the py-tgcalls recording file) directly to Gemini, receiving
spoken audio responses back.  This replaces the STT -> LLM -> TTS
pipeline with a single native audio-to-audio model.
"""

from __future__ import annotations

import array
import asyncio
import hashlib
import wave
from collections.abc import Awaitable, Callable
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

# ---------------------------------------------------------------------------
# Audio constants
# ---------------------------------------------------------------------------
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
PLAYBACK_SAMPLE_RATE = 48000
SEND_AUDIO_MIME = f"audio/pcm;rate={SEND_SAMPLE_RATE}"

WAV_HEADER_SIZE = 44
MIN_SEND_BYTES = 1600
MAX_TRANSCRIPT_ENTRIES = 200
TMPFS_DIR = Path("/dev/shm/secretary_ai")
GREETING_CACHE_DIR = Path(".telegram/cache")

# Sleep intervals (seconds)
POLL_WAIT_FILE = 0.3
POLL_WAIT_HEADER = 0.2
POLL_WAIT_DATA = 0.08
POLL_SEND_INTERVAL = 0.05
POLL_SEND_ERROR = 0.3
POLL_RECEIVE_ERROR = 0.3
POLL_PLAY_TIMEOUT = 10.0

# Logging cadence
LOG_EVERY_N_CHUNKS = 50

# ---------------------------------------------------------------------------
# Callback type aliases
# ---------------------------------------------------------------------------
StopCheck = Callable[[], bool]
DebugLog = Callable[[str, dict[str, Any]], None]
AudioOutCallback = Callable[[str], Awaitable[dict[str, Any]]]


def _resample_pcm16(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Resample 16-bit mono PCM by nearest-neighbour selection."""
    if src_rate == dst_rate:
        return data
    aligned = len(data) // 2 * 2
    src = array.array("h")
    src.frombytes(data[:aligned])
    ratio = src_rate / dst_rate
    n = len(src)
    dst_count = int(n / ratio)
    dst = array.array("h", (src[min(int(i * ratio), n - 1)] for i in range(dst_count)))
    return dst.tobytes()


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
        self._first_turn_complete = asyncio.Event()

    @staticmethod
    def available() -> bool:
        return _GENAI_AVAILABLE

    @staticmethod
    def _greeting_cache_key(language: str, voice: str, model: str) -> str:
        """Build a cache filename that includes voice and model."""
        fingerprint = hashlib.md5(f"{voice}:{model}".encode()).hexdigest()[:8]
        return f"gemini_greeting_{language}_{fingerprint}.wav"

    @staticmethod
    def cached_greeting_path(language: str, voice: str, model: str) -> Path | None:
        """Return the cached greeting WAV if it exists, else None."""
        name = GeminiLiveSession._greeting_cache_key(language, voice, model)
        path = GREETING_CACHE_DIR / name
        return path if path.is_file() else None

    def _build_client(self) -> Any:
        return genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=self.settings.gemini_api_key,
        )

    def _live_config(self) -> Any:
        from secretary_ai.core.locales import GEMINI_LIVE_SYSTEM_PROMPT, t

        system_prompt = t(GEMINI_LIVE_SYSTEM_PROMPT, self.settings.language)
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
        audio_out_callback: AudioOutCallback,
        stop_check: StopCheck,
        debug_log: DebugLog,
        greeting_played: bool = False,
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
            ``def(event, payload)`` for structured debug logging.
        greeting_played:
            If True, a cached greeting was already played before Gemini
            connected.  The initial prompt tells Gemini not to greet again.
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

                await self._send_initial_prompt(session, debug_log, greeting_played=greeting_played)

                tasks = [
                    asyncio.create_task(
                        self._send_audio_loop(session, recording_path, stop_check, debug_log)
                    ),
                    asyncio.create_task(
                        self._receive_audio_loop(session, stop_check, debug_log)
                    ),
                    asyncio.create_task(
                        self._play_audio_loop(
                            recording_path.parent,
                            recording_path.stem,
                            audio_out_callback,
                            stop_check,
                            debug_log,
                            greeting_played=greeting_played,
                        )
                    ),
                ]
                try:
                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in pending:
                        t.cancel()
                    if pending:
                        await asyncio.wait(pending)
                    for t in done:
                        if t.exception() is not None:
                            raise t.exception()  # type: ignore[misc]
                except asyncio.CancelledError:
                    raise
                finally:
                    for t in tasks:
                        if not t.done():
                            t.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            debug_log(
                "gemini_live_session_error",
                {"error": exc.__class__.__name__, "detail": str(exc)[:300]},
            )
        finally:
            self._running = False

    # ------------------------------------------------------------------
    # Initial prompt — triggers the greeting so the call isn't silent
    # ------------------------------------------------------------------

    async def _send_initial_prompt(
        self,
        session: Any,
        debug_log: DebugLog,
        *,
        greeting_played: bool = False,
    ) -> None:
        """Send a text turn so Gemini speaks a greeting without waiting for audio.

        Uses ``send_realtime_input(text=...)`` instead of
        ``send_client_content`` because the realtime path actually triggers
        Gemini to generate an audio response.

        When *greeting_played* is True a cached greeting was already streamed
        into the call, so we tell Gemini not to greet again.
        """
        from secretary_ai.core.locales import (
            GEMINI_LIVE_INITIAL_PROMPT,
            GEMINI_LIVE_RESUME_PROMPT,
            t,
        )

        mapping = GEMINI_LIVE_RESUME_PROMPT if greeting_played else GEMINI_LIVE_INITIAL_PROMPT
        prompt = t(mapping, self.settings.language)
        await session.send_realtime_input(text=prompt)
        debug_log(
            "gemini_live_initial_prompt_sent",
            {"prompt": prompt[:200], "greeting_played": greeting_played},
        )

    # ------------------------------------------------------------------
    # Send loop: recording WAV → Gemini
    # ------------------------------------------------------------------

    async def _send_audio_loop(
        self,
        session: Any,
        recording_path: Path,
        stop_check: StopCheck,
        debug_log: DebugLog,
    ) -> None:
        """Decode the recording file with ffmpeg and stream PCM to Gemini.

        py-tgcalls records to a WAV container using MP3 (libmp3lame) or
        FLAC codec — Python's ``wave`` module can only read raw PCM.
        We use ffmpeg with ``-ss`` to seek past already-decoded content
        so each invocation only decodes the *new* portion — O(n) total
        instead of the naive O(n²) approach of re-decoding everything.
        """
        decoded_seconds = 0.0
        chunks_sent = 0
        last_file_size = 0

        # Wait for the greeting turn to finish before forwarding caller
        # audio — otherwise Gemini interrupts its own greeting mid-sentence.
        try:
            await asyncio.wait_for(self._first_turn_complete.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            debug_log("gemini_live_send_wait_timeout", {})

        while not stop_check():
            if not recording_path.exists():
                await asyncio.sleep(POLL_WAIT_FILE)
                continue

            file_size = recording_path.stat().st_size
            if file_size <= WAV_HEADER_SIZE or file_size == last_file_size:
                await asyncio.sleep(POLL_WAIT_DATA)
                continue

            if file_size < last_file_size:
                debug_log(
                    "gemini_live_file_shrunk",
                    {"file_size": file_size, "last_file_size": last_file_size,
                     "decoded_seconds": decoded_seconds},
                )
                decoded_seconds = 0.0

            last_file_size = file_size

            cmd = ["ffmpeg", "-v", "error"]
            if decoded_seconds > 0:
                cmd += ["-ss", f"{decoded_seconds:.3f}"]
            cmd += [
                "-i", str(recording_path),
                "-f", "s16le", "-ar", str(SEND_SAMPLE_RATE), "-ac", "1",
                "pipe:1",
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
            except Exception:
                await asyncio.sleep(POLL_SEND_ERROR)
                continue

            if not stdout or len(stdout) < MIN_SEND_BYTES:
                await asyncio.sleep(POLL_WAIT_DATA)
                continue

            decoded_seconds += len(stdout) / (SEND_SAMPLE_RATE * 2)

            if chunks_sent == 0:
                debug_log("gemini_live_send_started", {"pcm_bytes": len(stdout)})

            try:
                await session.send_realtime_input(
                    audio=types.Blob(data=stdout, mimeType=SEND_AUDIO_MIME),
                )
                chunks_sent += 1
                if chunks_sent == 1 or chunks_sent % LOG_EVERY_N_CHUNKS == 0:
                    debug_log(
                        "gemini_live_audio_sent",
                        {"chunks": chunks_sent, "decoded_s": f"{decoded_seconds:.1f}"},
                    )
            except Exception as exc:
                debug_log(
                    "gemini_live_send_error",
                    {"error": exc.__class__.__name__, "detail": str(exc)[:200]},
                )
                await asyncio.sleep(POLL_SEND_ERROR)

            await asyncio.sleep(POLL_SEND_INTERVAL)

    # ------------------------------------------------------------------
    # Receive loop: Gemini → audio queue + transcripts
    # ------------------------------------------------------------------

    async def _receive_audio_loop(
        self,
        session: Any,
        stop_check: StopCheck,
        debug_log: DebugLog,
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
                        continue

                    audio_chunks = self._extract_audio(response, server_content)
                    for chunk in audio_chunks:
                        self.audio_out_queue.put_nowait(chunk)

                    self._record_transcripts(server_content, debug_log)

                    if getattr(server_content, "turn_complete", False):
                        self.audio_out_queue.put_nowait(b"")  # sentinel
                        turns_received += 1
                        if turns_received == 1:
                            self._first_turn_complete.set()
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
                await asyncio.sleep(POLL_RECEIVE_ERROR)

    def _record_transcripts(self, server_content: Any, debug_log: DebugLog) -> None:
        """Append input/output transcriptions and trim to bounded size."""
        input_tx = getattr(server_content, "input_transcription", None)
        if input_tx and getattr(input_tx, "text", None):
            self.transcript_in.append(input_tx.text)
            if len(self.transcript_in) > MAX_TRANSCRIPT_ENTRIES:
                self.transcript_in = self.transcript_in[-MAX_TRANSCRIPT_ENTRIES:]
            debug_log("gemini_live_input_transcript", {"text": input_tx.text[:200]})

        output_tx = getattr(server_content, "output_transcription", None)
        if output_tx and getattr(output_tx, "text", None):
            self.transcript_out.append(output_tx.text)
            if len(self.transcript_out) > MAX_TRANSCRIPT_ENTRIES:
                self.transcript_out = self.transcript_out[-MAX_TRANSCRIPT_ENTRIES:]
            debug_log("gemini_live_output_transcript", {"text": output_tx.text[:200]})

    # ------------------------------------------------------------------
    # Play loop: audio queue → WAV → Telegram call
    # ------------------------------------------------------------------

    async def _play_audio_loop(
        self,
        audio_dir: Path,
        call_prefix: str,
        audio_out_callback: AudioOutCallback,
        stop_check: StopCheck,
        debug_log: DebugLog,
        greeting_played: bool = False,
    ) -> None:
        """Accumulate audio for each Gemini turn, then play once.

        py-tgcalls ``play()`` **replaces** the current stream rather than
        queueing audio.  Playing many small WAVs in quick succession means
        each call interrupts the previous one and the user hears nothing.
        Instead we collect all PCM chunks until the turn-complete sentinel
        (``b""``) arrives, write one WAV, and call ``play()`` once per turn.
        """
        response_idx = 0
        out_dir = TMPFS_DIR if TMPFS_DIR.parent.is_dir() else audio_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        should_cache = not greeting_played
        turn_chunks: list[bytes] = []

        while not stop_check():
            try:
                chunk = await asyncio.wait_for(
                    self.audio_out_queue.get(), timeout=POLL_PLAY_TIMEOUT
                )
            except asyncio.TimeoutError:
                # Safety-net flush: only fires if the sentinel is lost.
                # Never cache the greeting here — the turn may be incomplete.
                if turn_chunks:
                    debug_log("gemini_live_timeout_flush", {"chunks": len(turn_chunks)})
                    await self._flush_turn(
                        turn_chunks, out_dir, call_prefix, response_idx,
                        audio_out_callback, debug_log, cache_greeting=False,
                    )
                    turn_chunks.clear()
                    response_idx += 1
                continue

            if chunk == b"":
                # Sentinel: turn complete — play the accumulated audio.
                if turn_chunks:
                    await self._flush_turn(
                        turn_chunks, out_dir, call_prefix, response_idx,
                        audio_out_callback, debug_log, should_cache,
                    )
                    if should_cache:
                        should_cache = False
                    turn_chunks.clear()
                    response_idx += 1
                continue

            turn_chunks.append(chunk)

    async def _flush_turn(
        self,
        chunks: list[bytes],
        out_dir: Path,
        call_prefix: str,
        response_idx: int,
        audio_out_callback: AudioOutCallback,
        debug_log: DebugLog,
        cache_greeting: bool,
    ) -> None:
        """Write accumulated PCM chunks as a single WAV and play it."""
        pcm_data = b"".join(chunks)
        pcm_48k = _resample_pcm16(pcm_data, RECEIVE_SAMPLE_RATE, PLAYBACK_SAMPLE_RATE)
        # Pad 300 ms of silence so py-tgcalls ffmpeg fully drains the tail.
        pcm_48k += b"\x00" * (2 * PLAYBACK_SAMPLE_RATE * 300 // 1000)

        wav_path = out_dir / f"gemini_{call_prefix}_{response_idx}.wav"
        try:
            await asyncio.to_thread(_write_wav, wav_path, pcm_48k, PLAYBACK_SAMPLE_RATE)
        except Exception as exc:
            debug_log(
                "gemini_live_wav_write_error",
                {"error": exc.__class__.__name__, "path": str(wav_path)},
            )
            return

        if cache_greeting:
            await self._cache_greeting(pcm_48k, debug_log)

        try:
            result = await audio_out_callback(str(wav_path))
            status = result.get("status") if isinstance(result, dict) else str(result)
            detail = result.get("detail", "") if isinstance(result, dict) else ""
            log_data: dict[str, object] = {
                "idx": response_idx, "bytes": len(pcm_data), "status": status,
            }
            if detail:
                log_data["detail"] = str(detail)[:300]
            debug_log("gemini_live_audio_played", log_data)
        except Exception as exc:
            debug_log(
                "gemini_live_play_error",
                {"error": exc.__class__.__name__, "detail": str(exc)[:200]},
            )
        finally:
            wav_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _cache_greeting(self, pcm_48k: bytes, debug_log: DebugLog) -> None:
        """Write the complete first-turn PCM as a greeting WAV cache file."""
        try:
            GREETING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            name = self._greeting_cache_key(
                self.settings.language, self.settings.gemini_live_voice, self.settings.gemini_live_model,
            )
            cache_path = GREETING_CACHE_DIR / name
            await asyncio.to_thread(_write_wav, cache_path, pcm_48k, PLAYBACK_SAMPLE_RATE)
            debug_log("gemini_greeting_cached", {"path": str(cache_path), "bytes": len(pcm_48k)})
        except Exception as exc:
            debug_log("gemini_greeting_cache_error", {"error": exc.__class__.__name__})

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


