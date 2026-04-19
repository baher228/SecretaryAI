"""
Background reminder loop.
Every minute, checks:
- Google Calendar events starting in ~55-65 minutes
- Tasks with due_at in ~55-65 minutes

Sends a Telegram push to all ALLOWED_TELEGRAM_IDS for each new match.
Tracks sent reminders in-memory to avoid duplicates within a session.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from aiogram import Bot

from db.session import AsyncSessionLocal
from db.models import Task
from service.google_calendar import list_events
from bot.config import ALLOWED_TELEGRAM_IDS

logger = logging.getLogger(__name__)

_sent_event_ids: set[str] = set()
_sent_task_ids: set[int] = set()

CHECK_INTERVAL_SEC = 60
LEAD_MINUTES = 60
WINDOW_MINUTES = 6


async def _format_event_reminder(event: dict, minutes_until: int) -> str:
    title = event.get("summary", "Event")
    start = event.get("start", "")
    location = event.get("location")
    html_link = event.get("html_link", "")

    parts = [f"⏰ <b>In {minutes_until} minutes:</b> {title}"]
    if start:
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            local = dt.astimezone(ZoneInfo("Europe/London"))
            parts.append(f"🕐 {local.strftime('%I:%M %p')}")
        except Exception:
            pass
    if location:
        parts.append(f"📍 {location}")
    if html_link:
        parts.append(f'<a href="{html_link}">Open in Calendar</a>')
    return "\n".join(parts)


async def _format_task_reminder(task: Task, minutes_until: int) -> str:
    parts = [f"⏰ <b>Task due in {minutes_until} minutes:</b>"]
    parts.append(f"📌 {task.description}")
    parts.append(f"<i>Task ID {task.id}</i>")
    return "\n".join(parts)


async def _check_calendar(bot: Bot):
    """Check Google Calendar for events starting in the lead window."""
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(minutes=LEAD_MINUTES - WINDOW_MINUTES / 2)
    window_end = now + timedelta(minutes=LEAD_MINUTES + WINDOW_MINUTES / 2)

    events = await list_events(
        start_iso=window_start.isoformat().replace("+00:00", "Z"),
        end_iso=window_end.isoformat().replace("+00:00", "Z"),
        max_results=20,
    )

    for event in events:
        if "error" in event:
            logger.warning(f"Calendar check error: {event['error']}")
            continue
        eid = event.get("id")
        if not eid or eid in _sent_event_ids:
            continue

        start_str = event.get("start", "")
        try:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            minutes_until = int((start_dt - now).total_seconds() / 60)
        except Exception:
            minutes_until = LEAD_MINUTES

        message = await _format_event_reminder(event, minutes_until)
        await _broadcast(bot, message)
        _sent_event_ids.add(eid)
        logger.info(f"Sent calendar reminder for event {eid}")


async def _check_tasks(bot: Bot):
    """Check DB for tasks with due_at in the lead window."""
    now = datetime.utcnow()
    window_start = now + timedelta(minutes=LEAD_MINUTES - WINDOW_MINUTES / 2)
    window_end = now + timedelta(minutes=LEAD_MINUTES + WINDOW_MINUTES / 2)

    async with AsyncSessionLocal() as s:
        q = select(Task).where(
            Task.status == "open",
            Task.due_at.is_not(None),
            Task.due_at >= window_start,
            Task.due_at <= window_end,
        )
        tasks = (await s.execute(q)).scalars().all()

    for task in tasks:
        if task.id in _sent_task_ids:
            continue

        minutes_until = int((task.due_at - now).total_seconds() / 60)
        message = await _format_task_reminder(task, minutes_until)
        await _broadcast(bot, message)
        _sent_task_ids.add(task.id)
        logger.info(f"Sent task reminder for task {task.id}")


async def _broadcast(bot: Bot, text: str):
    """Send message to all whitelisted users."""
    for uid in ALLOWED_TELEGRAM_IDS:
        try:
            await bot.send_message(uid, text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"Failed to send reminder to {uid}: {e}")


async def reminder_loop(bot: Bot):
    """Main loop — called as a background task from main.py."""
    logger.info(f"Reminder loop started. Lead time: {LEAD_MINUTES} min, check every {CHECK_INTERVAL_SEC}s")
    while True:
        try:
            await _check_calendar(bot)
            await _check_tasks(bot)
        except Exception as e:
            logger.exception(f"Reminder loop iteration failed: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
