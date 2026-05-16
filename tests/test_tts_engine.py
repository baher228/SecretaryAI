import asyncio
from unittest.mock import MagicMock, patch

from secretary_ai.core.config import Settings
from secretary_ai.services.tts import TTSEngine


def test_resolve_edge_voice_supports_polly_alias() -> None:
    assert TTSEngine._resolve_edge_voice("Polly.Joanna") == "en-US-JennyNeural"


def test_resolve_edge_voice_defaults_when_empty() -> None:
    assert TTSEngine._resolve_edge_voice("") == "en-US-AriaNeural"


def test_resolve_edge_voice_passthrough() -> None:
    assert TTSEngine._resolve_edge_voice("ru-RU-DmitryNeural") == "ru-RU-DmitryNeural"


def test_synthesize_rejects_empty_text() -> None:
    engine = TTSEngine(Settings(tts_enabled=True))
    path, status = asyncio.run(engine.synthesize("   ", "call-1"))
    assert path is None
    assert status == "empty_text"


def test_synthesize_respects_disabled_flag() -> None:
    engine = TTSEngine(Settings(tts_enabled=False))
    path, status = asyncio.run(engine.synthesize("hello", "call-2"))
    assert path is None
    assert status == "disabled"


def test_synthesize_rejects_unknown_provider() -> None:
    engine = TTSEngine(Settings(tts_enabled=True, tts_provider="unknown_provider"))
    path, status = asyncio.run(engine.synthesize("hello", "call-3"))
    assert path is None
    assert status == "unsupported_provider:unknown_provider"


def test_synthesize_routes_to_silero() -> None:
    """Verify that tts_provider=silero routes to the Silero synthesizer."""
    settings = Settings(tts_enabled=True, tts_provider="silero")
    engine = TTSEngine(settings)
    with patch.object(engine, "_synthesize_silero", return_value=(None, "mocked")) as mock:
        path, status = asyncio.run(engine.synthesize("Привет", "call-4"))
        mock.assert_called_once_with("Привет", "call-4")
    assert status == "mocked"


def test_synthesize_routes_to_edge() -> None:
    """Verify that tts_provider=edge_tts routes to the Edge TTS synthesizer."""
    settings = Settings(tts_enabled=True, tts_provider="edge_tts")
    engine = TTSEngine(settings)
    with patch.object(engine, "_synthesize_edge", return_value=(None, "mocked_edge")) as mock:
        path, status = asyncio.run(engine.synthesize("Hello", "call-5"))
        mock.assert_called_once_with("Hello", "call-5")
    assert status == "mocked_edge"


def test_silero_config_defaults() -> None:
    """Default Silero settings are sensible for Russian."""
    s = Settings()
    assert s.tts_silero_model_id == "v5_5_ru"
    assert s.tts_silero_speaker == "xenia"
    assert s.tts_silero_sample_rate == 48000
    assert s.tts_silero_device == "cpu"


def test_silero_model_load_failure_falls_back_to_edge() -> None:
    """If Silero is unavailable, synthesis falls back to Edge TTS."""
    settings = Settings(tts_enabled=True, tts_provider="silero")
    engine = TTSEngine(settings)

    with patch("secretary_ai.services.tts._get_silero_model", side_effect=RuntimeError("no torch")):
        path, status = asyncio.run(engine.synthesize("Привет", "call-6"))
    # Falls back to Edge TTS which should produce a file
    assert path is not None
    assert status == "generated"


def test_silero_synthesis_success() -> None:
    """Silero synthesis writes a WAV file when the model works."""
    settings = Settings(
        tts_enabled=True,
        tts_provider="silero",
        tts_silero_speaker="xenia",
        tts_silero_sample_rate=48000,
        telegram_audio_root="/tmp/secretary_test_audio",
    )
    engine = TTSEngine(settings)

    mock_model = MagicMock()
    mock_model.save_wav = MagicMock(return_value=None)

    async def _fake_get_model(_settings: Settings) -> MagicMock:
        return mock_model

    with patch("secretary_ai.services.tts._get_silero_model", side_effect=_fake_get_model):
        path, status = asyncio.run(engine.synthesize("Тест голоса", "call-7"))

    assert status == "generated"
    assert path is not None
    assert path.endswith(".wav")
    mock_model.save_wav.assert_called_once()
    call_kwargs = mock_model.save_wav.call_args
    assert call_kwargs[1]["text"] == "Тест голоса"
    assert call_kwargs[1]["speaker"] == "xenia"
    assert call_kwargs[1]["sample_rate"] == 48000


def test_available_providers_includes_edge() -> None:
    providers = TTSEngine.available_providers()
    assert "edge_tts" in providers


def test_silero_voices_locale_data() -> None:
    from secretary_ai.core.locales import SILERO_VOICES

    ru_voices = SILERO_VOICES.get("ru", [])
    assert len(ru_voices) == 5
    names = {v["id"] for v in ru_voices}
    assert names == {"aidar", "baya", "kseniya", "xenia", "eugene"}
    for v in ru_voices:
        assert "gender" in v
        assert "name" in v
