import json
import time
from datetime import datetime
from typing import AsyncIterator
from zoneinfo import ZoneInfo
from openai import AsyncOpenAI
from bot.config import ZAI_API_KEY, ZAI_BASE_URL, ZAI_MODEL
from bot.tools import TOOL_SCHEMAS, execute_tool

client = AsyncOpenAI(api_key=ZAI_API_KEY, base_url=ZAI_BASE_URL)

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

## Concierge behaviors (when user wants to book/plan something)

When user asks to find restaurants, hotels, events, travel, or plan an evening:

1. Use the appropriate search_* tool to get REAL data (real names, addresses, prices, ratings from the web).

2. After getting results, present 2-3 best options as a compact HTML list with:
   - <b>Name</b>
   - One-line description with key detail (cuisine, rating, distance)
   - <a href="URL">View</a> link to the actual source

3. For each option, invent 2-3 plausible "booking slots" — specific times that realistically could be available. Frame them honestly:
   - <i>"I'd typically check these times — tap one and I'll add it to your calendar with the booking link."</i>
   - NEVER claim you actually called or booked. User understands they'll finalize via the link.

4. Attach [[BUTTONS:]] marker with one button per slot, callback_data format:
   `book:TYPE:TIMESTAMP:NAME` where TYPE is one of restaurant/hotel/event/travel, TIMESTAMP is ISO start time (YYYY-MM-DDTHH:MM, exactly 16 chars), NAME is shortened venue name (max 20 chars, no colons).
   Example: `[[BUTTONS: 🍽️ 7:30 PM=book:restaurant:2026-04-20T19:30:Bocca di Lupo | 🍽️ 8:00 PM=book:restaurant:2026-04-20T20:00:Bocca di Lupo ;; 🍽️ 8:30 PM=book:restaurant:2026-04-20T20:30:Bocca di Lupo]]`

5. When user clicks a slot button:
   - You'll receive a synthetic user message like `[User chose booking slot: type=restaurant, time=2026-04-20T19:30, venue=Bocca di Lupo]`
   - Create the calendar event via gcal_create_event (duration: 90 min for restaurant, 3 hours for event, 2 days for hotel check-in, fixed times for travel)
   - Format the response using the "Post-action message style" section below.

6. For plan_evening: compose a timeline like "7pm Dinner at X → 9pm Show at Y" with slot buttons for each component.

## Post-action message style (CRITICAL for polish)

After ANY successful action (create event, delete event, create task, complete task, book slot), output a compact celebratory message with this structure:

Line 1: Emoji + short verb ("🎉 Booked!", "✨ Added", "✅ Completed", "🗑️ Removed", "📅 Scheduled")
Blank line
Lines 2-4: Key details with emoji prefixes:
- 📌 for item name/title
- 📅 for date
- 🕐 for time range
- 📍 for location (if any)
- 🔗 for external link (inline <a href>, NEVER a button)

Blank line
Divider line: ━━━━━━━━━━━━━━
Blank line

Close with [[BUTTONS: ...]] marker containing 1 contextual follow-up action. Keep labels short (under 15 chars).

Button sets per action type:
- CREATE EVENT: [[BUTTONS: 🗑️ Remove=event:delete:EVENT_ID]]
- DELETE EVENT: [[BUTTONS: 📋 View calendar=cmd:calendar]]
- CREATE TASK: [[BUTTONS: 📋 All tasks=cmd:tasks]]
- COMPLETE TASK: [[BUTTONS: 📋 What's next=cmd:tasks]]
- BOOKING SLOT (concierge): [[BUTTONS: 📅 View calendar=cmd:calendar]]

Example:

🎉 <b>Booked!</b>

📌 <b>Collapse test</b>
📅 Tomorrow, Sun Apr 20
🕐 5:00 PM – 5:30 PM
🔗 <a href="https://calendar.google.com/...">Open in Calendar</a>

━━━━━━━━━━━━━━

[[BUTTONS: 🗑️ Remove=event:delete:abc123]]

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
Follow the "Post-action message style" section above. Include a single contextual [[BUTTONS:]] — no default keyboard for these.

### Format reminder
- `;;` splits rows, `|` splits buttons within a row, `=` splits label from callback_data
- Max 2 rows, max 3 buttons per row
- Callback_data prefixes: confirm:, task:, call:, contact:, event:, cmd:

## BEHAVIOR RULES

**ABSOLUTE RULE — you must not violate this:** Before calling gcal_create_event, you MUST first call gcal_find_free_slots with a window covering the requested time. If results show the slot is busy, DO NOT create. Reply with alternatives and ask the user to pick. No exceptions unless the user explicitly says "create anyway" or "ignore conflicts".

- Confirm before destructive actions if intent is ambiguous.
- Reference calls by date + counterpart: "Tuesday's call with Maria".
- Use list_recent_calls first, get_call_details only if user wants more.
- For calendar mutations (create/update/delete): always confirm title, date, and time with the user in natural language BEFORE calling the tool.
- When user says "tomorrow 3pm" or similar relative times, resolve using Europe/London timezone. Current date is available from system clock.
- Never narrate your reasoning process or tool selection in responses. The user only sees your final answer. Don't say "let me check", "let me try", "UID conflicts", or any similar internal monologue.
- Respond in English."""


def build_system_prompt() -> str:
    now = datetime.now(ZoneInfo("Europe/London"))
    context = (
        f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')} ({now.strftime('%Z')})\n"
        'When the user says "tomorrow", "next week", etc., resolve relative to this current date.\n'
    )
    return context + "\n\n" + _SYSTEM_PROMPT_TEMPLATE


async def run_agent(user_message: str, history: list, stream: bool = True) -> AsyncIterator[tuple[str, list | None]]:
    """
    Yields (chunk, None) for incremental text deltas.
    Final yield is ("", updated_history) as a sentinel to hand back the final history.
    """
    t0 = time.perf_counter()
    messages = [{"role": "system", "content": build_system_prompt()}] + history + [
        {"role": "user", "content": user_message}
    ]

    for iteration in range(1, 11):
        t_call = time.perf_counter()
        response = await client.chat.completions.create(
            model=ZAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            extra_body={"thinking": {"type": "disabled"}},
        )
        print(f"[agent] iter={iteration} glm_call={time.perf_counter()-t_call:.2f}s", flush=True)

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            print(f"[agent] total={time.perf_counter()-t0:.2f}s iterations={iteration}", flush=True)
            yield (msg.content or "", None)
            out_history = [m for m in messages if m.get("role") != "system"]
            yield ("", out_history)
            return

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            t_tool = time.perf_counter()
            result = await execute_tool(call.function.name, args)
            print(f"[agent] tool={call.function.name} dur={time.perf_counter()-t_tool:.3f}s", flush=True)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

        if stream:
            t_stream = time.perf_counter()
            stream_resp = await client.chat.completions.create(
                model=ZAI_MODEL,
                messages=messages,
                extra_body={"thinking": {"type": "disabled"}},
                stream=True,
            )

            full_text = ""
            chunk_count = 0
            first_chunk_t = None
            async for chunk in stream_resp:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    delta_content = chunk.choices[0].delta.content
                    chunk_count += 1
                    if first_chunk_t is None:
                        first_chunk_t = time.perf_counter() - t_stream
                        print(f"[agent] first_chunk_at={first_chunk_t:.2f}s len={len(delta_content)}", flush=True)
                    full_text += delta_content
                    yield (delta_content, None)

            print(f"[agent] stream_call={time.perf_counter()-t_stream:.2f}s chunks={chunk_count}", flush=True)
            print(f"[agent] total={time.perf_counter()-t0:.2f}s iterations=stream", flush=True)

            if not full_text.strip():
                print("[agent] empty stream — retrying non-streaming", flush=True)
                fallback = await client.chat.completions.create(
                    model=ZAI_MODEL,
                    messages=messages,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                full_text = fallback.choices[0].message.content or "(no response generated)"
                yield (full_text, None)
        else:
            t_nostream = time.perf_counter()
            response2 = await client.chat.completions.create(
                model=ZAI_MODEL,
                messages=messages,
                extra_body={"thinking": {"type": "disabled"}},
            )
            full_text = response2.choices[0].message.content or "(no response generated)"
            print(f"[agent] nonstream_call={time.perf_counter()-t_nostream:.2f}s", flush=True)
            print(f"[agent] total={time.perf_counter()-t0:.2f}s iterations=nonstream", flush=True)
            yield (full_text, None)

        messages.append({"role": "assistant", "content": full_text})
        out_history = [m for m in messages if m.get("role") != "system"]
        yield ("", out_history)
        return

    print(f"[agent] total={time.perf_counter()-t0:.2f}s LIMIT REACHED", flush=True)
    yield ("Reached tool-call iteration limit.", None)
    yield ("", [m for m in messages if m.get("role") != "system"])
