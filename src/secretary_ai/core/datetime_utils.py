"""Shared datetime parsing utilities used across services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 string and return a UTC-aware datetime, or *None*."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_event_start(event: dict) -> datetime | None:
    """Extract and parse the ``start`` field from a calendar-event dict."""
    raw = str(event.get("start") or "").strip()
    if not raw:
        return None
    if len(raw) == 10 and raw.count("-") == 2:
        raw = f"{raw}T09:00:00+00:00"
    return parse_iso(raw)


def humanize_iso_datetime(value: str) -> str:
    """Turn an ISO timestamp into a human-friendly phrase like *today at 3:00 PM*."""
    if not value:
        return ""
    parsed = parse_iso(value)
    if parsed is None:
        return ""
    local = parsed.astimezone()
    day = local.strftime("%A")
    now = datetime.now(local.tzinfo).date()
    if local.date() == now:
        day = "today"
    elif local.date() == (now + timedelta(days=1)):
        day = "tomorrow"
    return f"{day} at {local.strftime('%I:%M %p').lstrip('0')}"
