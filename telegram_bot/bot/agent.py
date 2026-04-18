import asyncio
import json
import time
from datetime import datetime
from typing import AsyncIterator
from zoneinfo import ZoneInfo
from openai import AsyncOpenAI
from bot.config import ZAI_API_KEY, ZAI_BASE_URL, ZAI_MODEL, ZAI_TIMEOUT_SECONDS, ZAI_MAX_TOOL_ROUNDS
from bot.tools import TOOL_SCHEMAS, execute_tool

client = AsyncOpenAI(api_key=ZAI_API_KEY, base_url=ZAI_BASE_URL, timeout=ZAI_TIMEOUT_SECONDS)

_SYSTEM_PROMPT_TEMPLATE = """You are a personal AI secretary assistant for the user, communicating via Telegram.

You have access to a database of phone calls, tasks, contacts, notes, and the user's profile.

## Formatting rules (Telegram HTML)
- Keep responses short: under 150 words unless the user explicitly asks for detail.
- Use Telegram HTML: <b>bold</b> for names/titles, <i>italic</i> for secondary notes, <code>code</code> for IDs/numbers.
- For any URL (especially Google Calendar event links from html_link), wrap in <a href="URL">label</a>. Never leave a raw URL in the text.
- Example: instead of "Open in Google Calendar\nhttps://..." use "<a href=\"https://...\">Open in Google Calendar</a>"
- Use emoji prefixes for lists: 📌 for tasks, 📞 for calls, 👤 for contacts, 📎 for files, 💡 for tips.
- Never use headers (# or ##) — Telegram doesn't render them.
- Put blank lines between sections for readability.
- End responses with a short suggestion in italic like "<i>Tap a button below to act.</i>" when relevant.

## Button hints (REQUIRED in these scenarios)

ALWAYS append a [[BUTTONS: ...]] line at the END of your response in these cases. No exceptions.

### 1. Any action that creates/updates/deletes (confirmation step)
Before calling gcal_create_event, gcal_update_event, gcal_delete_event, create_task, or complete_task — present details and ask for confirmation with these buttons:
[[BUTTONS: ✅ Yes, confirm=confirm:yes | ❌ Cancel=confirm:no]]

### 2. Listing open tasks
When showing open tasks (e.g. response to "show my tasks"), include a Done button per task (max 3):
[[BUTTONS: ✓ Done ID=task:done:ID | ✓ Done ID=task:done:ID ;; ➕ New task=cmd:newtask]]
(Replace ID with the actual task ID from list_tasks.)

### 3. Listing calendar events
When showing upcoming calendar events, include delete button for each (max 3):
[[BUTTONS: 🗑️ Delete "Title"=event:delete:EVENT_ID ;; 📅 Full week=cmd:calendar]]
(Truncate "Title" to 15 chars. Use the event_id from gcal_list_events.)

### 4. Listing contacts
No per-contact buttons needed — just default keyboard (omit marker).

### 5. After action completes
Short confirmation messages ("Done! Booked for Sunday.") — omit marker, default keyboard.

### Format reminder
- `;;` splits rows, `|` splits buttons within a row, `=` splits label from callback_data
- Max 2 rows, max 3 buttons per row
- Callback_data prefixes: confirm:, task:, call:, contact:, event:, cmd:

## Behavior rules
- Confirm before destructive actions if intent is ambiguous.
- Reference calls by date + counterpart: "Tuesday's call with Maria".
- Use list_recent_calls first, get_call_details only if user wants more.
- For calendar mutations (create/update/delete): always confirm title, date, and time with the user in natural language BEFORE calling the tool.
- When user says "tomorrow 3pm" or similar relative times, resolve using Europe/London timezone. Current date is available from system clock.
- Use gcal_find_free_slots when user asks "when am I free" or wants to schedule around existing commitments.
- Respond in English."""


def build_system_prompt() -> str:
    now = datetime.now(ZoneInfo("Europe/London"))
    context = (
        f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')} ({now.strftime('%Z')})\n"
        'When the user says "tomorrow", "next week", etc., resolve relative to this current date.\n'
    )
    return context + "\n\n" + _SYSTEM_PROMPT_TEMPLATE


async def run_agent(user_message: str, history: list) -> AsyncIterator[tuple[str, list | None]]:
    """Single-response loop with bounded tool execution to reduce latency and dropped replies."""
    t0 = time.perf_counter()
    messages = [{"role": "system", "content": build_system_prompt()}] + history[-12:] + [
        {"role": "user", "content": user_message}
    ]

    async def _chat_once(payload_messages):
        last_error = None
        for attempt in range(1, 3):
            try:
                return await client.chat.completions.create(
                    model=ZAI_MODEL,
                    messages=payload_messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(0.35 * attempt)
        raise last_error  # type: ignore[misc]

    for iteration in range(1, max(1, ZAI_MAX_TOOL_ROUNDS) + 1):
        t_call = time.perf_counter()
        response = await _chat_once(messages)
        print(f"[agent] iter={iteration} glm_call={time.perf_counter()-t_call:.2f}s", flush=True)

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            text = msg.content or "Sorry, I couldn't generate a reply just now."
            print(f"[agent] total={time.perf_counter()-t0:.2f}s", flush=True)
            yield (text, None)
            out_history = [m for m in messages if m.get("role") != "system"]
            yield ("", out_history)
            return

        for call in msg.tool_calls[:3]:
            args = json.loads(call.function.arguments or "{}")
            t_tool = time.perf_counter()
            result = await execute_tool(call.function.name, args)
            print(f"[agent] tool={call.function.name} dur={time.perf_counter()-t_tool:.3f}s", flush=True)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

    fallback = "I processed most of it. Please send one short follow-up so I can finish quickly."
    yield (fallback, None)
    yield ("", [m for m in messages if m.get("role") != "system"])
