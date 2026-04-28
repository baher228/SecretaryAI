from secretary_ai.core.config import Settings
import secretary_ai.services.stt as stt_module
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


def test_transcribe_recent_only_does_not_retry_full_file(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"fake")
    clip = tmp_path / "sample-tail.wav"
    clip.write_bytes(b"clip")

    engine = STTEngine(Settings(stt_recent_only=True))
    monkeypatch.setattr(stt_module, "WhisperModel", object)
    monkeypatch.setattr(engine, "_ensure_model", lambda: object())

    async def fake_extract_recent(path):
        return clip

    calls = {"count": 0}

    def fake_transcribe_with_model(model, path):
        calls["count"] += 1
        return ""

    monkeypatch.setattr(engine, "_extract_recent_clip", fake_extract_recent)
    monkeypatch.setattr(engine, "_transcribe_with_model", fake_transcribe_with_model)

    text, status = __import__("asyncio").run(engine.transcribe(str(audio)))
    assert text == ""
    assert status == "no_speech"
    assert calls["count"] == 1
