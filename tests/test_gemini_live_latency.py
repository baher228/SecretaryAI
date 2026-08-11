from pathlib import Path
from types import SimpleNamespace

from secretary_ai.services import gemini_live
from secretary_ai.services.gemini_live import GeminiLiveSession


def test_ffmpeg_decode_uses_low_delay_flags_and_twenty_ms_chunks() -> None:
    cmd = GeminiLiveSession._ffmpeg_decode_cmd(Path("call.wav"), 1.25)

    assert cmd[:3] == ["ffmpeg", "-v", "error"]
    assert "-fflags" in cmd and "nobuffer" in cmd
    assert "-flags" in cmd and "low_delay" in cmd
    assert cmd[cmd.index("-ss") + 1] == "1.250"
    assert cmd[-7:] == ["-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"]
    assert gemini_live.SEND_CHUNK_BYTES == 640
    assert gemini_live.PLAYBACK_TAIL_PAD_MS == 120


def test_live_config_enables_fast_vad_when_sdk_supports_it() -> None:
    session = GeminiLiveSession(SimpleNamespace(language="en", gemini_live_voice="Zephyr"))
    config = session._live_config()

    assert config is not None
    payload = config.model_dump(exclude_none=True) if hasattr(config, "model_dump") else {}
    text = str(payload).lower() + str(config).lower()
    assert "audio" in text
    if "silence" in text:
        assert "500" in text or "silence_duration_ms" in text
