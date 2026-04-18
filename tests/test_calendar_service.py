import asyncio

from secretary_ai.core.config import Settings
from secretary_ai.services.calendar import CalendarService


def test_quick_reply_reads_from_cache(tmp_path) -> None:
    cache = tmp_path / "calendar_cache.json"
    queue = tmp_path / "calendar_queue.json"
    service = CalendarService(
        Settings(
            calendar_enabled=True,
            calendar_cache_path=str(cache),
            calendar_queue_path=str(queue),
        )
    )
    service.cache = {
        "updated_at": "2026-04-18T23:00:00+00:00",
        "events": [
            {
                "id": "e1",
                "summary": "Team standup",
                "start": "2999-01-01T09:00:00+00:00",
                "end": "2999-01-01T09:30:00+00:00",
            }
        ],
    }

    result = asyncio.run(
        service.quick_reply_or_enqueue(
            call_id="tg-1",
            transcript="what's on my calendar today",
            context={},
        )
    )

    assert result["status"] == "served_from_cache"
    assert result["queued"] is False
    assert "Upcoming:" in result["reply"]


def test_quick_reply_enqueues_mutation(tmp_path) -> None:
    cache = tmp_path / "calendar_cache.json"
    queue = tmp_path / "calendar_queue.json"
    service = CalendarService(
        Settings(
            calendar_enabled=True,
            calendar_cache_path=str(cache),
            calendar_queue_path=str(queue),
        )
    )

    result = asyncio.run(
        service.quick_reply_or_enqueue(
            call_id="tg-2",
            transcript="please schedule lunch with Alex tomorrow",
            context={"source": "test"},
        )
    )

    assert result["status"] == "queued"
    assert result["queued"] is True
    assert len(service.queue) == 1


def test_process_queue_applies_cache_only_create_when_provider_unavailable(tmp_path) -> None:
    cache = tmp_path / "calendar_cache.json"
    queue = tmp_path / "calendar_queue.json"
    service = CalendarService(
        Settings(
            calendar_enabled=True,
            calendar_cache_path=str(cache),
            calendar_queue_path=str(queue),
            calendar_id=None,
            calendar_service_account_json=None,
        )
    )

    asyncio.run(
        service.quick_reply_or_enqueue(
            call_id="tg-3",
            transcript="create event about roadmap review",
            context={},
        )
    )
    result = asyncio.run(service.process_queue(max_items=2))

    assert result["processed"] == 1
    assert len(service.cache.get("events", [])) == 1
    assert service.queue[0]["status"] in {"done", "failed"}
    assert service.queue[0].get("result") is not None
