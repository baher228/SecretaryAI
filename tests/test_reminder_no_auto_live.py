import asyncio

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import OutboundCallRequest, OutboundCallResponse, OutboundPurpose
from secretary_ai.services.secretary import SecretaryService


def test_reminder_outbound_call_does_not_auto_start_live_loop() -> None:
    service = SecretaryService(Settings(telegram_auto_start_live_agent=True, assistant_auto_greet_on_connect=True))

    async def fake_start_outbound_call(target_user, purpose, initial_audio_path, metadata):
        return {
            "call_id": "tg-1",
            "status": "active",
            "detail": "ok",
            "provider": "telegram_mtproto",
            "chat_id": 1,
        }

    called = {"live": 0}

    async def fake_live_start(call_id, payload, greeting_played=False):
        called["live"] += 1
        raise AssertionError("live loop should not start for reminder announcement calls")

    service.telegram.start_outbound_call = fake_start_outbound_call  # type: ignore[method-assign]
    service.start_telegram_live_agent = fake_live_start  # type: ignore[method-assign]

    payload = OutboundCallRequest(
        target_user="@gringobochka",
        purpose=OutboundPurpose.REMINDER,
        initial_audio_path="/app/.telegram/audio/generated/reminder-x.mp3",
        metadata={"source": "calendar_reminder", "announcement_only": True},
    )
    response = asyncio.run(service.start_outbound_call(payload))

    assert isinstance(response, OutboundCallResponse)
    assert response.status == "active"
    assert called["live"] == 0


def test_regular_reminder_purpose_still_uses_live_loop_when_not_announcement() -> None:
    service = SecretaryService(
        Settings(
            telegram_auto_start_live_agent=True,
            assistant_auto_greet_on_connect=False,
        )
    )

    async def fake_start_outbound_call(target_user, purpose, initial_audio_path, metadata):
        return {
            "call_id": "tg-2",
            "status": "active",
            "detail": "ok",
            "provider": "telegram_mtproto",
            "chat_id": 2,
        }

    called = {"live": 0}

    async def fake_live_start(call_id, payload, greeting_played=False):
        called["live"] += 1
        return type("R", (), {"status": "running", "detail": "ok"})()

    service.telegram.start_outbound_call = fake_start_outbound_call  # type: ignore[method-assign]
    service.start_telegram_live_agent = fake_live_start  # type: ignore[method-assign]

    payload = OutboundCallRequest(
        target_user="@gringobochka",
        purpose=OutboundPurpose.REMINDER,
        initial_audio_path=None,
        metadata={"source": "manual_test"},
    )
    response = asyncio.run(service.start_outbound_call(payload))

    assert isinstance(response, OutboundCallResponse)
    assert response.status == "active"
    assert called["live"] == 1
