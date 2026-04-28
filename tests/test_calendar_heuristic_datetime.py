from secretary_ai.core.config import Settings
from secretary_ai.services.calendar import CalendarService


def test_extract_datetime_from_text_parses_common_time() -> None:
    service = CalendarService(Settings(calendar_enabled=True))
    parsed = service._extract_datetime_from_text("schedule meeting tomorrow at 3:30 pm")
    assert parsed is not None
    assert parsed.hour == 15
    assert parsed.minute == 30


def test_extract_datetime_from_text_parses_dot_time_without_ampm() -> None:
    service = CalendarService(Settings(calendar_enabled=True))
    parsed = service._extract_datetime_from_text("set a reminder today at 11.35")
    assert parsed is not None
    assert parsed.hour == 11
    assert parsed.minute == 35


def test_plan_action_heuristic_uses_context_start_end() -> None:
    service = CalendarService(Settings(calendar_enabled=True))
    task = {
        "transcript": "schedule event for this time",
        "context": {
            "start_iso": "2030-01-01T10:15:00+00:00",
            "end_iso": "2030-01-01T10:45:00+00:00",
        },
    }
    plan = service._plan_action_heuristic(task)
    assert plan["action"] == "create"
    assert str(plan["start_iso"]).startswith("2030-01-01T10:15:00")
    assert str(plan["end_iso"]).startswith("2030-01-01T10:45:00")
