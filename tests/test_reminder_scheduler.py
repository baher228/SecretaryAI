import asyncio
from datetime import datetime, timedelta, timezone

from secretary_ai.core.config import Settings
from secretary_ai.services.secretary import SecretaryService


def test_schedule_event_reminder_writes_state(tmp_path) -> None:
    state_path = tmp_path / "reminder_state.json"
    settings = Settings(
        reminder_enabled=True,
        reminder_state_path=str(state_path),
        reminder_lead_minutes=60,
        reminder_scan_horizon_hours=72,
        tts_enabled=True,
    )
    service = SecretaryService(settings)

    async def fake_synthesize(text: str, call_id: str) -> tuple[str | None, str]:
        return str(tmp_path / f"{call_id}.mp3"), "generated"

    service.tts.synthesize = fake_synthesize  # type: ignore[method-assign]

    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(hours=1)
    event = {
        "id": "evt-1",
        "summary": "Design review",
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    asyncio.run(service._schedule_event_reminder(event=event, target_user="5523073095", call_id="tg-1"))

    assert "evt-1" in service._reminder_state
    item = service._reminder_state["evt-1"]
    assert item.get("target_user") == "5523073095"
    assert item.get("status") == "scheduled"
    assert str(item.get("audio_path") or "").endswith(".mp3")


def test_parse_event_start_accepts_all_day_event() -> None:
    event = {"id": "evt-day", "start": "2099-01-10"}
    parsed = SecretaryService._parse_event_start(event)
    assert parsed is not None
    assert parsed.year == 2099
