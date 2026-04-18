import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bot.config import GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_CALENDAR_ID

SCOPES = ["https://www.googleapis.com/auth/calendar"]
_service = None


def _get_service():
    global _service
    if _service is None:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def _event_to_dict(ev: dict) -> dict:
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary"),
        "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
        "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
        "description": ev.get("description"),
        "location": ev.get("location"),
        "attendees": [a.get("email") for a in ev.get("attendees", []) if a.get("email")],
        "html_link": ev.get("htmlLink"),
    }


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- list_events ----------

def _list_events_sync(start_iso, end_iso, max_results):
    now = datetime.now(timezone.utc)
    t_min = start_iso or now.isoformat()
    t_max = end_iso or (now + timedelta(days=7)).isoformat()
    try:
        svc = _get_service()
        resp = svc.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=t_min,
            timeMax=t_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return [_event_to_dict(e) for e in resp.get("items", [])]
    except HttpError as e:
        return [{"error": str(e)}]


async def list_events(start_iso: str | None = None, end_iso: str | None = None, max_results: int = 20):
    return await asyncio.to_thread(_list_events_sync, start_iso, end_iso, max_results)


# ---------- create_event ----------

def _create_event_sync(title, start_iso, end_iso, description, location, attendees, timezone_name):
    body = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": timezone_name},
        "end": {"dateTime": end_iso, "timeZone": timezone_name},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    try:
        svc = _get_service()
        ev = svc.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()
        return {
            "id": ev.get("id"),
            "html_link": ev.get("htmlLink"),
            "start": (ev.get("start") or {}).get("dateTime"),
            "end": (ev.get("end") or {}).get("dateTime"),
            "status": "created",
        }
    except HttpError as e:
        return {"error": str(e)}


async def create_event(
    title: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone_name: str = "Europe/London",
):
    return await asyncio.to_thread(
        _create_event_sync, title, start_iso, end_iso, description, location, attendees, timezone_name
    )


# ---------- update_event ----------

def _update_event_sync(event_id, changes):
    try:
        svc = _get_service()
        ev = svc.events().patch(
            calendarId=GOOGLE_CALENDAR_ID, eventId=event_id, body=changes
        ).execute()
        return {
            "id": ev.get("id"),
            "summary": ev.get("summary"),
            "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
            "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
            "status": "updated",
        }
    except HttpError as e:
        return {"error": str(e)}


async def update_event(event_id: str, changes: dict):
    return await asyncio.to_thread(_update_event_sync, event_id, changes)


# ---------- delete_event ----------

def _delete_event_sync(event_id):
    try:
        svc = _get_service()
        svc.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
        return {"id": event_id, "status": "deleted"}
    except HttpError as e:
        return {"id": event_id, "error": str(e)}


async def delete_event(event_id: str):
    return await asyncio.to_thread(_delete_event_sync, event_id)


# ---------- find_free_slots ----------

def _find_free_slots_sync(duration_minutes, date_range_start_iso, date_range_end_iso, working_hours):
    try:
        svc = _get_service()
        resp = svc.freebusy().query(body={
            "timeMin": date_range_start_iso,
            "timeMax": date_range_end_iso,
            "items": [{"id": GOOGLE_CALENDAR_ID}],
            "timeZone": "Europe/London",
        }).execute()
        busy = resp["calendars"][GOOGLE_CALENDAR_ID].get("busy", [])

        tz = ZoneInfo("Europe/London")
        start_dt = _parse_iso(date_range_start_iso).astimezone(tz)
        end_dt = _parse_iso(date_range_end_iso).astimezone(tz)
        busy_ranges = sorted(
            (_parse_iso(b["start"]).astimezone(tz), _parse_iso(b["end"]).astimezone(tz))
            for b in busy
        )

        duration = timedelta(minutes=duration_minutes)
        wh_start, wh_end = working_hours
        slots: list[dict] = []

        day = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        while day.date() <= end_dt.date() and len(slots) < 10:
            day_start = day.replace(hour=wh_start)
            day_end = day.replace(hour=wh_end)
            if day_start < start_dt:
                day_start = start_dt
            if day_end > end_dt:
                day_end = end_dt
            if day_start >= day_end:
                day = day + timedelta(days=1)
                continue

            cursor = day_start
            day_busy = [(bs, be) for bs, be in busy_ranges if bs < day_end and be > day_start]
            for bs, be in day_busy:
                if cursor + duration <= bs:
                    slots.append({"start": cursor.isoformat(), "end": (cursor + duration).isoformat()})
                    if len(slots) >= 10:
                        break
                if be > cursor:
                    cursor = be
            if len(slots) < 10 and cursor + duration <= day_end:
                slots.append({"start": cursor.isoformat(), "end": (cursor + duration).isoformat()})

            day = day + timedelta(days=1)
        return slots[:10]
    except HttpError as e:
        return [{"error": str(e)}]


async def find_free_slots(
    duration_minutes: int,
    date_range_start_iso: str,
    date_range_end_iso: str,
    working_hours: tuple[int, int] = (9, 18),
):
    return await asyncio.to_thread(
        _find_free_slots_sync, duration_minutes, date_range_start_iso, date_range_end_iso, working_hours
    )
