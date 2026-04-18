from secretary_ai.core.config import Settings
from secretary_ai.services.stt import STTEngine


def test_transcribe_returns_missing_file_for_unknown_path() -> None:
    engine = STTEngine(Settings())
    text, status = __import__("asyncio").run(engine.transcribe("/tmp/not-real-audio.wav"))
    assert text == ""
    assert status == "missing_audio_file"


def test_transcribe_respects_disabled_flag(tmp_path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"x")
    engine = STTEngine(Settings(stt_enabled=False))
    text, status = __import__("asyncio").run(engine.transcribe(str(audio)))
    assert text == ""
    assert status == "disabled"


def test_bundled_ffmpeg_path_returns_none_or_string() -> None:
    value = STTEngine._bundled_ffmpeg_path()
    assert value is None or isinstance(value, str)
