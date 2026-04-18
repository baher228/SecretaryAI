import asyncio

from secretary_ai.core.config import Settings
from secretary_ai.services.telegram_calls import TelegramCallService


class _FakeCalls:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.play_calls = []

    async def play(self, chat_id, stream=None):
        self.play_calls.append((chat_id, stream))
        if self.should_fail:
            raise RuntimeError("play failed")


def build_service() -> TelegramCallService:
    return TelegramCallService(Settings())


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
