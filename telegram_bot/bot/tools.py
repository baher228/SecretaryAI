import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy import select, desc
from db.session import AsyncSessionLocal
from db.models import Call, Task, UserContext
from service.google_calendar import (
    list_events as _gcal_list_events,
    create_event as _gcal_create_event,
    update_event as _gcal_update_event,
    delete_event as _gcal_delete_event,
    find_free_slots as _gcal_find_free_slots,
)
from service.search import tavily_search

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_recent_calls",
            "description": "List recent phone calls with summaries. Default: last 7 days, up to 10 calls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "days_back": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_call_details",
            "description": "Get full transcript and metadata for a specific call by ID.",
            "parameters": {
                "type": "object",
                "properties": {"call_id": {"type": "integer"}},
                "required": ["call_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task. due_at is optional, ISO 8601 format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "due_at": {"type": "string"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List tasks. status can be: open, done, or all. Default: open.",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as done by its ID.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_list_events",
            "description": "List events from Google Calendar. Defaults to next 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_iso": {"type": "string"},
                    "end_iso": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_create_event",
            "description": "Create a new calendar event. ALWAYS confirm details with the user before calling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start_iso": {"type": "string"},
                    "end_iso": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "start_iso", "end_iso"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_update_event",
            "description": "Update an existing event. Must have event_id from list_events. Always confirm with user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "changes": {"type": "object"},
                },
                "required": ["event_id", "changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_delete_event",
            "description": "Delete an event. Always confirm with user first.",
            "parameters": {
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_find_free_slots",
            "description": "Find free time slots of given duration in working hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_minutes": {"type": "integer"},
                    "date_range_start_iso": {"type": "string"},
                    "date_range_end_iso": {"type": "string"},
                },
                "required": ["duration_minutes", "date_range_start_iso", "date_range_end_iso"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_restaurants",
            "description": "Search the web for real restaurants. Returns a list of {title, url, content, score}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "cuisine": {"type": "string"},
                    "price_range": {"type": "string", "description": "$, $$, or $$$"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search the web for real hotels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "check_in": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "check_out": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "budget": {"type": "string"},
                },
                "required": ["location", "check_in", "check_out"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Search the web for concerts, theatre, cinema, sports, or exhibitions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "event_type": {"type": "string", "description": "concert, theatre, cinema, sports, exhibition"},
                    "date": {"type": "string", "description": "ISO date or 'this weekend' etc."},
                },
                "required": ["location", "event_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_travel",
            "description": "Search the web for flight, train, or bus options between two places.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "mode": {"type": "string", "description": "flight, train, or bus"},
                    "return_date": {"type": "string"},
                },
                "required": ["origin", "destination", "date", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_evening",
            "description": "Compose a full evening plan: dinner + entertainment. Runs two web searches internally. Returns {dinner, entertainment} each a list of results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "preferences": {"type": "string", "description": "e.g. 'romantic, italian, jazz'"},
                },
                "required": ["location", "date"],
            },
        },
    },
]


async def _list_recent_calls(limit: int = 10, days_back: int = 7):
    async with AsyncSessionLocal() as s:
        since = datetime.utcnow() - timedelta(days=days_back)
        q = select(Call).where(Call.started_at >= since).order_by(desc(Call.started_at)).limit(limit)
        rows = (await s.execute(q)).scalars().all()
        return [
            {"id": c.id, "started_at": c.started_at.isoformat(),
             "caller_name": c.caller_name, "summary": c.summary}
            for c in rows
        ]


async def _get_call_details(call_id: int):
    async with AsyncSessionLocal() as s:
        c = await s.get(Call, call_id)
        if not c:
            return {"error": "not_found"}
        return {
            "id": c.id,
            "started_at": c.started_at.isoformat(),
            "ended_at": c.ended_at.isoformat() if c.ended_at else None,
            "caller_name": c.caller_name,
            "caller_number": c.caller_number,
            "transcript": c.transcript,
            "summary": c.summary,
        }


async def _create_task(description: str, due_at: str | None = None):
    async with AsyncSessionLocal() as s:
        t = Task(
            description=description,
            due_at=datetime.fromisoformat(due_at) if due_at else None,
        )
        s.add(t)
        await s.commit()
        return {"id": t.id, "status": "created"}


async def _list_tasks(status: str = "open"):
    async with AsyncSessionLocal() as s:
        q = select(Task).order_by(desc(Task.created_at))
        if status != "all":
            q = q.where(Task.status == status)
        rows = (await s.execute(q)).scalars().all()
        return [
            {"id": t.id, "description": t.description,
             "due_at": t.due_at.isoformat() if t.due_at else None,
             "status": t.status}
            for t in rows
        ]


async def _store_context(kind: str, content: str, file_path: str | None = None):
    async with AsyncSessionLocal() as s:
        entry = UserContext(kind=kind, content=content, file_path=file_path)
        s.add(entry)
        await s.commit()
        return {"id": entry.id, "status": "stored"}


async def _complete_task(task_id: int):
    async with AsyncSessionLocal() as s:
        t = await s.get(Task, task_id)
        if not t:
            return {"error": "not_found"}
        t.status = "done"
        await s.commit()
        return {"id": t.id, "status": "done"}


_RESTAURANT_DOMAINS = ["opentable.com", "timeout.com", "resy.com", "tripadvisor.com"]
_HOTEL_DOMAINS = ["booking.com", "hotels.com", "airbnb.com", "expedia.com"]
_EVENT_DOMAINS = ["ticketmaster.com", "seetickets.com", "timeout.com", "eventbrite.com"]
_FLIGHT_DOMAINS = ["skyscanner.net", "kayak.com", "google.com"]
_TRAIN_DOMAINS = ["nationalrail.co.uk", "trainline.com", "raileurope.com"]
_BUS_DOMAINS = ["nationalexpress.com", "megabus.com", "flixbus.com"]


async def _search_restaurants(location: str, cuisine: str | None = None, price_range: str | None = None):
    parts = ["best"]
    if cuisine:
        parts.append(cuisine)
    parts.append("restaurants in")
    parts.append(location)
    if price_range:
        parts.append(price_range)
    return await tavily_search(" ".join(parts), max_results=5, include_domains=_RESTAURANT_DOMAINS)


async def _search_hotels(location: str, check_in: str, check_out: str, budget: str | None = None):
    parts = [f"hotels in {location} {check_in} to {check_out}"]
    if budget:
        parts.append(budget)
    return await tavily_search(" ".join(parts), max_results=5, include_domains=_HOTEL_DOMAINS)


async def _search_events(location: str, event_type: str, date: str | None = None):
    parts = [event_type, "in", location]
    if date:
        parts.append(date)
    return await tavily_search(" ".join(parts), max_results=5, include_domains=_EVENT_DOMAINS)


async def _search_travel(origin: str, destination: str, date: str, mode: str, return_date: str | None = None):
    mode_l = (mode or "").lower()
    if mode_l == "train":
        domains = _TRAIN_DOMAINS
    elif mode_l == "bus":
        domains = _BUS_DOMAINS
    else:
        domains = _FLIGHT_DOMAINS
    q = f"{mode} from {origin} to {destination} on {date}"
    if return_date:
        q += f" return {return_date}"
    return await tavily_search(q, max_results=5, include_domains=domains)


async def _plan_evening(location: str, date: str, preferences: str | None = None):
    pref = preferences or ""
    dinner_q = f"dinner restaurants in {location} {date} {pref}".strip()
    ent_q = f"theatre concerts bars in {location} {date} {pref}".strip()
    dinner, entertainment = await asyncio.gather(
        tavily_search(dinner_q, max_results=3, include_domains=_RESTAURANT_DOMAINS),
        tavily_search(ent_q, max_results=3, include_domains=_EVENT_DOMAINS),
    )
    return {"dinner": dinner, "entertainment": entertainment}


HANDLERS = {
    "list_recent_calls": _list_recent_calls,
    "get_call_details": _get_call_details,
    "create_task": _create_task,
    "list_tasks": _list_tasks,
    "complete_task": _complete_task,
    "gcal_list_events": _gcal_list_events,
    "gcal_create_event": _gcal_create_event,
    "gcal_update_event": _gcal_update_event,
    "gcal_delete_event": _gcal_delete_event,
    "gcal_find_free_slots": _gcal_find_free_slots,
    "search_restaurants": _search_restaurants,
    "search_hotels": _search_hotels,
    "search_events": _search_events,
    "search_travel": _search_travel,
    "plan_evening": _plan_evening,
}


async def execute_tool(name: str, params: dict):
    if name not in HANDLERS:
        return {"error": f"unknown tool: {name}"}
    try:
        return await HANDLERS[name](**params)
    except Exception as e:
        return {"error": str(e)}
