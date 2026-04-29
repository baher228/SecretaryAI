import asyncio
from datetime import datetime, timedelta, timezone

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import CallAudioResponse, TelegramLiveAgentStartRequest
from secretary_ai.services.secretary import SecretaryService


def test_should_ignore_live_snippet_filters_ivr_noise() -> None:
    assert SecretaryService._should_ignore_live_snippet("Please hold while we connect your call.") is True
    assert SecretaryService._should_ignore_live_snippet("The number you have dialed cannot be completed.") is True


def test_should_ignore_live_snippet_keeps_real_user_request() -> None:
    assert SecretaryService._should_ignore_live_snippet("Can you remind me to call John tomorrow?") is False


def test_should_ignore_live_snippet_keeps_time_phrase() -> None:
    assert SecretaryService._should_ignore_live_snippet("5 PM.") is False


def test_fast_fallback_sets_live_pause_when_audio_streams() -> None:
    service = SecretaryService(Settings())
    service.live_sessions["tg-1"] = {"pause_until": None}

    async def fake_synthesize(text: str, call_id: str) -> tuple[str | None, str]:
        return "fake.mp3", "generated"

    async def fake_stream_audio_out(call_id: str, audio_path: str) -> dict[str, str]:
        return {"status": "streaming_out", "detail": "ok"}

    service.tts.synthesize = fake_synthesize  # type: ignore[method-assign]
    service.telegram.stream_audio_out = fake_stream_audio_out  # type: ignore[method-assign]

    async def run() -> None:
        await service._fast_fallback_response(
            call_id="tg-1",
            snippet="set reminder",
            reply="queued",
            action_item="x",
            speak_response=True,
        )

    asyncio.run(run())
    pause_until = service.live_sessions["tg-1"].get("pause_until")
    assert isinstance(pause_until, datetime)
    assert pause_until > datetime.now(timezone.utc)


def test_reminder_time_followup_enqueues_and_confirms() -> None:
    service = SecretaryService(Settings())
    service._reminder_flow_state["tg-1"] = {
        "completed_at": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
        "fingerprint": "abc",
        "awaiting_result": False,
    }

    async def fake_queue(call_id: str, transcript: str, context: dict | None = None) -> dict[str, object]:
        assert "set a reminder today at 5 PM" == transcript
        return {"queued": True, "task_id": "cal-123", "reply": "queued"}

    async def fake_fast_response(call_id: str, snippet: str, reply: str, action_item: str, speak_response: bool):
        class _Resp:
            def __init__(self) -> None:
                self.action_items = [action_item]

        assert "Done. Reminder set for today at 5 PM." in reply
        return _Resp()

    service.calendar.quick_reply_or_enqueue = fake_queue  # type: ignore[method-assign]
    service._fast_fallback_response = fake_fast_response  # type: ignore[method-assign]

    async def run() -> None:
        result = await service._maybe_handle_reminder_time_followup(
            call_id="tg-1",
            transcript="5 PM.",
            speak_response=True,
        )
        assert result is not None
        assert "calendar_queue:cal-123" in result.action_items

    asyncio.run(run())


def test_live_agent_replies_with_immediate_calendar_result() -> None:
    service = SecretaryService(Settings(calendar_enabled=True))

    async def fake_quick_reply_or_enqueue(call_id: str, transcript: str, context: dict | None = None):
        return {
            "status": "queued",
            "queued": True,
            "task_id": "cal-1",
            "reply": "Got it. I queued this calendar request and will apply it shortly.",
        }

    async def fake_process_queue(max_items: int = 5):
        return {
            "status": "ok",
            "processed": 1,
            "results": [
                {
                    "task_id": "cal-1",
                    "status": "done",
                    "result": {
                        "status": "ok",
                        "detail": "Event created in provider.",
                        "event": {
                            "summary": "Buy stocks",
                            "start": "2030-01-01T17:00:00+00:00",
                        },
                    },
                }
            ],
        }

    service.calendar.quick_reply_or_enqueue = fake_quick_reply_or_enqueue  # type: ignore[method-assign]
    service.calendar.process_queue = fake_process_queue  # type: ignore[method-assign]

    async def run() -> None:
        response = await service.live_agent_respond(
            call_id="tg-imm",
            transcript="set reminder today at five",
            context={"source": "telegram_live_loop"},
            speak_response=False,
        )
        assert "Done. Scheduled 'Buy stocks'" in response.reply
        assert "calendar_processed:done" in response.action_items

    asyncio.run(run())


def test_start_live_agent_resets_per_call_state_and_uses_fresh_recording(tmp_path) -> None:
    service = SecretaryService(
        Settings(
            telegram_audio_root=str(tmp_path / "audio"),
            calendar_enabled=False,
            gemini_api_key="test-key",
        )
    )

    service._template_reply_state["tg-1"] = {"thanks": {"last_at": "2026-01-01T00:00:00+00:00"}}
    service._reminder_flow_state["tg-1"] = {"fingerprint": "abc"}
    service.memory.add_short_term_turn("tg-1", "old transcript", "old reply")

    async def fake_stream_audio_in(call_id, payload):
        return CallAudioResponse(call_id=call_id, status="recording_in", detail="ok")

    async def fake_gemini_loop(call_id, recording_path, greeting_played=False):
        return

    service.stream_audio_in = fake_stream_audio_in  # type: ignore[method-assign]
    service._telegram_gemini_live_loop = fake_gemini_loop  # type: ignore[method-assign]
    service.telegram.get_call = lambda call_id: {"status": "active"}  # type: ignore[method-assign]

    async def run() -> None:
        response = await service.start_telegram_live_agent(
            "tg-1",
            TelegramLiveAgentStartRequest(context={"source": "test"}, speak_response=False),
        )
        assert response.status == "running"
        assert response.recording_path is not None
        assert "tg-1-" in response.recording_path
        assert response.recording_path.endswith(".wav")
        assert "tg-1" not in service._template_reply_state
        assert "tg-1" not in service._reminder_flow_state
        calls = service.memory.short_term.get("calls", {})
        assert "tg-1" not in calls

    asyncio.run(run())
