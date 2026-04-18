import asyncio

from secretary_ai.core.config import Settings
from secretary_ai.services.telegram_calls import TelegramCallService


class _FakeCalls:
    def __init__(self, should_fail: bool = False, error_message: str = "play failed") -> None:
        self.should_fail = should_fail
        self.error_message = error_message
        self.play_calls = []

    async def play(self, chat_id, stream=None):
        self.play_calls.append((chat_id, stream))
        if self.should_fail:
            raise RuntimeError(self.error_message)


def build_service() -> TelegramCallService:
    service = TelegramCallService(Settings())
    service._ffmpeg_available = lambda: True  # type: ignore[method-assign]
    return service


def test_start_outbound_call_requires_authorized_state() -> None:
    service = build_service()

    async def scenario():
        service._can_place_calls = lambda: asyncio.sleep(0, result=False)  # type: ignore[method-assign]
        return await service.start_outbound_call("@target", "reminder", None, {})

    result = asyncio.run(scenario())
    assert result["status"] == "not_authorized"


def test_start_outbound_call_returns_invalid_target_when_not_resolved() -> None:
    service = build_service()

    async def scenario():
        service._can_place_calls = lambda: asyncio.sleep(0, result=True)  # type: ignore[method-assign]
        service._resolve_chat_id = lambda target: asyncio.sleep(0, result=None)  # type: ignore[method-assign]
        return await service.start_outbound_call("bad_target", "reminder", None, {})

    result = asyncio.run(scenario())
    assert result["status"] == "invalid_target"


def test_start_outbound_call_becomes_active_on_successful_play() -> None:
    service = build_service()
    service._calls = _FakeCalls()

    async def scenario():
        service._can_place_calls = lambda: asyncio.sleep(0, result=True)  # type: ignore[method-assign]
        service._resolve_chat_id = lambda target: asyncio.sleep(0, result=12345)  # type: ignore[method-assign]
        return await service.start_outbound_call("@good", "reminder", None, {"source": "test"})

    result = asyncio.run(scenario())
    assert result["status"] == "active"
    assert result["call_id"] == "tg-12345"
    assert service.calls["tg-12345"]["status"] == "active"


def test_start_outbound_call_returns_failed_when_provider_play_throws() -> None:
    service = build_service()
    service._calls = _FakeCalls(should_fail=True)

    async def scenario():
        service._can_place_calls = lambda: asyncio.sleep(0, result=True)  # type: ignore[method-assign]
        service._resolve_chat_id = lambda target: asyncio.sleep(0, result=54321)  # type: ignore[method-assign]
        return await service.start_outbound_call("@good", "reminder", None, {})

    result = asyncio.run(scenario())
    assert result["status"] == "failed"
    assert service.calls["tg-54321"]["status"] == "failed"


def test_readiness_reports_missing_ffmpeg() -> None:
    service = TelegramCallService(Settings())
    service._library_ready = lambda: True  # type: ignore[method-assign]
    service._credentials_ready = lambda: True  # type: ignore[method-assign]
    service._ffmpeg_available = lambda: False  # type: ignore[method-assign]

    ok, detail = service.readiness()
    assert ok is False
    assert "ffmpeg" in detail.lower()


def test_stream_audio_out_includes_underlying_error_message() -> None:
    service = build_service()
    call_id = "tg-111"
    chat_id = 111

    service.calls[call_id] = {"call_id": call_id, "chat_id": chat_id, "status": "active"}
    service._calls = _FakeCalls(should_fail=True, error_message="ffmpeg not found")

    async def scenario():
        service._can_place_calls = lambda: asyncio.sleep(0, result=True)  # type: ignore[method-assign]
        return await service.stream_audio_out(call_id, __file__)

    result = asyncio.run(scenario())
    assert result["status"] == "error"
    assert "ffmpeg" in result["detail"].lower()
