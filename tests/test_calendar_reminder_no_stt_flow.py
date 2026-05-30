import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import OutboundCallResponse
from secretary_ai.services.secretary import SecretaryService


def test_calendar_reminder_flow_without_stt_triggers_call_to_fixed_user(tmp_path: Path) -> None:
    settings = Settings(
        openai_api_key=None,
        calendar_enabled=True,
        calendar_id=None,
        calendar_service_account_json=None,
        calendar_cache_path=str(tmp_path / "calendar_events.json"),
        calendar_queue_path=str(tmp_path / "calendar_queue.json"),
        reminder_enabled=True,
        reminder_target_user="@gringobochka",
        reminder_lead_minutes=60,
        reminder_state_path=str(tmp_path / "reminder_state.json"),
        reminder_scan_horizon_hours=72,
        tts_enabled=True,
    )
    service = SecretaryService(settings)

    async def fake_synthesize(text: str, call_id: str) -> tuple[str | None, str]:
        out = tmp_path / f"{call_id}.mp3"
        out.write_bytes(b"fake-audio")
        return str(out), "generated"

    captured: dict[str, str] = {}

    async def fake_start_outbound_call(payload):
        captured["target_user"] = payload.target_user
        return OutboundCallResponse(
            call_id="tg-reminder-1",
            status="active",
            detail="mock reminder call started",
        )

    service.tts.synthesize = fake_synthesize  # type: ignore[method-assign]
    service.start_outbound_call = fake_start_outbound_call  # type: ignore[method-assign]

    start = datetime.now(timezone.utc) + timedelta(hours=1)
    end = start + timedelta(minutes=30)
    transcript = "set a reminder to buy stocks today at some time like in an hour"

    async def run_flow() -> None:
        queued = await service.calendar.quick_reply_or_enqueue(
            call_id="tg-5523073095",
            transcript=transcript,
            context={"start_iso": start.isoformat(), "end_iso": end.isoformat()},
        )
        assert queued.get("queued") is True

        queue_result = await service.calendar.process_queue(max_items=2)
        await service._maybe_schedule_reminders_from_queue_result(queue_result)
        assert service._reminder_state

        # Simulate "an hour before event" moment reached.
        for state in service._reminder_state.values():
            state["remind_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

        await service._dispatch_due_reminder_calls()

    asyncio.run(run_flow())

    assert captured.get("target_user") == "@gringobochka"
    assert any(v.get("status") == "called" for v in service._reminder_state.values())
