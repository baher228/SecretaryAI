"""
Build a markdown context block for injection into the OpenAI Realtime
session's system prompt. Called when an incoming call arrives.
"""
from datetime import datetime, timedelta
from sqlalchemy import select, desc
from db.session import AsyncSessionLocal
from db.models import (
    Call, Task, UserContext, Contact, UserProfile, StandingInstruction
)

RECENT_CALLS_LIMIT = 10
RECENT_CALLS_DAYS = 30


async def build_voice_context(caller_phone: str | None = None) -> str:
    """
    Assemble a compact markdown block with everything the voice agent
    needs to know about the user and their world at call start.

    If caller_phone is provided, that contact is pinned to the top
    (caller identification).
    """
    async with AsyncSessionLocal() as s:
        profile = (await s.execute(select(UserProfile).limit(1))).scalar_one_or_none()

        pinned_contact = None
        if caller_phone:
            q = select(Contact).where(Contact.phone_number == caller_phone)
            pinned_contact = (await s.execute(q)).scalar_one_or_none()

        cutoff = datetime.utcnow() - timedelta(days=RECENT_CALLS_DAYS)
        recent_calls_q = (
            select(Call)
            .where(Call.started_at >= cutoff)
            .order_by(desc(Call.started_at))
            .limit(RECENT_CALLS_LIMIT)
        )
        recent_calls = (await s.execute(recent_calls_q)).scalars().all()

        open_tasks = (await s.execute(
            select(Task).where(Task.status == "open").order_by(Task.due_at.asc().nullslast())
        )).scalars().all()

        instructions = (await s.execute(
            select(StandingInstruction)
            .where(StandingInstruction.active == True)
            .order_by(desc(StandingInstruction.priority))
        )).scalars().all()

        notes = (await s.execute(
            select(UserContext).order_by(desc(UserContext.created_at)).limit(10)
        )).scalars().all()

        contacts = (await s.execute(
            select(Contact).order_by(desc(Contact.updated_at)).limit(20)
        )).scalars().all()

    parts = ["# User context for this call", ""]

    if profile:
        parts.append("## About the user")
        if profile.full_name:
            parts.append(f"- Name: {profile.full_name}")
        if profile.role:
            parts.append(f"- Role: {profile.role}")
        parts.append(f"- Timezone: {profile.timezone}")
        if profile.working_hours:
            parts.append(f"- Working hours: {profile.working_hours}")
        if profile.communication_style:
            parts.append(f"- Communication style: {profile.communication_style}")
        parts.append("")

    if pinned_contact:
        parts.append("## Current caller")
        parts.append(f"- **{pinned_contact.name}** ({pinned_contact.phone_number})")
        if pinned_contact.company:
            parts.append(f"  - Company: {pinned_contact.company}")
        if pinned_contact.role:
            parts.append(f"  - Role: {pinned_contact.role}")
        if pinned_contact.notes:
            parts.append(f"  - Notes: {pinned_contact.notes}")
        parts.append("")

    if instructions:
        parts.append("## Standing instructions (must follow)")
        for ins in instructions:
            parts.append(f"- {ins.instruction}")
        parts.append("")

    if open_tasks:
        parts.append("## Open tasks")
        for t in open_tasks:
            due = f" (due {t.due_at.strftime('%Y-%m-%d')})" if t.due_at else ""
            parts.append(f"- {t.description}{due}")
        parts.append("")

    if recent_calls:
        parts.append("## Recent calls")
        for c in recent_calls:
            when = c.started_at.strftime("%Y-%m-%d")
            who = c.caller_name or c.caller_number or "Unknown"
            summary = c.summary or "(no summary)"
            parts.append(f"- [{when}] {who}: {summary}")
        parts.append("")

    if contacts:
        parts.append("## Known contacts")
        for c in contacts:
            line = f"- {c.name}"
            if c.phone_number:
                line += f" ({c.phone_number})"
            if c.company:
                line += f" — {c.company}"
            if c.notes:
                line += f" — {c.notes}"
            parts.append(line)
        parts.append("")

    if notes:
        parts.append("## Recent notes and files")
        for n in notes:
            line = f"- [{n.kind}] {n.content}"
            if n.file_path:
                line += f" (file: {n.file_path})"
            parts.append(line)
        parts.append("")

    return "\n".join(parts)
