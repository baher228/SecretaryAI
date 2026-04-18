from secretary_ai.core.config import Settings
from secretary_ai.services.tts import TTSEngine


def test_resolve_voice_name_supports_polly_alias() -> None:
    assert TTSEngine._resolve_voice_name("Polly.Joanna") == "en-US-JennyNeural"


def test_resolve_voice_name_defaults_when_empty() -> None:
    assert TTSEngine._resolve_voice_name("") == "en-US-AriaNeural"


def test_synthesize_rejects_empty_text() -> None:
    engine = TTSEngine(Settings(tts_enabled=True))
    path, status = __import__("asyncio").run(engine.synthesize("   ", "call-1"))
    assert path is None
    assert status == "empty_text"


def test_synthesize_respects_disabled_flag() -> None:
    engine = TTSEngine(Settings(tts_enabled=False))
    path, status = __import__("asyncio").run(engine.synthesize("hello", "call-2"))
    assert path is None
    assert status == "disabled"
