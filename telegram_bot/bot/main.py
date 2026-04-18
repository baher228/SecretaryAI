import asyncio
import re
import time
import uuid
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BotCommand, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from bot.config import TELEGRAM_BOT_TOKEN, OWNER_TELEGRAM_ID, ALLOWED_TELEGRAM_IDS
from bot.agent import run_agent
from bot.files import (
    UPLOAD_DIR, extract_pdf_text, summarize_document,
    describe_image, transcribe_audio,
)
from bot.tools import _store_context
from db.session import init_db

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

sessions: dict[int, list] = {}


WELCOME = """👋 <b>Hey, I'm your AI secretary.</b>

I manage your calls, tasks, contacts, and notes. During live phone calls I also help the voice agent know what you care about.

Try asking:
- <i>"What tasks do I have?"</i>
- <i>"Who called me this week?"</i>
- <i>"Remind me to email Maria tomorrow at 3pm"</i>
- Send me a file to save for later

<i>Tap a button below or just type.</i>"""


CALLBACK_PROMPTS = {
    "cmd:tasks": "Show my open tasks",
    "cmd:calls": "Show my recent calls",
    "cmd:contacts": "Show my contacts",
    "cmd:newtask": "I want to add a new task. Ask me what it should be.",
    "cmd:help": "Briefly list what you can help me with. Keep it under 100 words, use emojis.",
    "cmd:calendar": "Show my calendar for this week",
    "cmd:edit": "Let me edit the last thing you proposed.",
    "cmd:concierge": "What can you help me find? I can search for restaurants, hotels, events, travel options, or plan a full evening. Just tell me what you need.",
}


BUTTONS_PATTERN = re.compile(r"\[\[BUTTONS:\s*(.+?)\]\]", re.DOTALL)


def strip_button_marker_for_streaming(text: str) -> str:
    """Hide any partial or complete [[BUTTONS:...]] marker during intermediate streaming edits."""
    match = BUTTONS_PATTERN.search(text)
    if match:
        return BUTTONS_PATTERN.sub("", text).rstrip()
    idx = text.find("[[BUTTONS:")
    if idx != -1:
        return text[:idx].rstrip()
    return text


def extract_buttons(text: str) -> tuple[str, "InlineKeyboardMarkup | None"]:
    """Extract [[BUTTONS:...]] marker from text. Returns (clean_text, keyboard_or_None)."""
    match = BUTTONS_PATTERN.search(text)
    if not match:
        return text, None

    spec = match.group(1).strip()
    clean_text = BUTTONS_PATTERN.sub("", text).strip()

    kb = InlineKeyboardBuilder()
    rows = [r.strip() for r in spec.split(";;") if r.strip()]
    row_sizes: list[int] = []

    for row in rows:
        buttons = [b.strip() for b in row.split("|") if b.strip()]
        count = 0
        for btn in buttons:
            if "=" not in btn:
                continue
            label, _, data = btn.partition("=")
            kb.button(text=label.strip(), callback_data=data.strip())
            count += 1
        if count > 0:
            row_sizes.append(count)

    if not row_sizes:
        return clean_text, None

    kb.adjust(*row_sizes)
    return clean_text, kb.as_markup()


def is_allowed(message: Message) -> bool:
    return message.from_user.id in ALLOWED_TELEGRAM_IDS


def build_default_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Tasks", callback_data="cmd:tasks")
    kb.button(text="📅 Calendar", callback_data="cmd:calendar")
    kb.button(text="📞 Calls", callback_data="cmd:calls")
    kb.button(text="👤 Contacts", callback_data="cmd:contacts")
    kb.button(text="🍽️ Concierge", callback_data="cmd:concierge")
    kb.button(text="➕ New task", callback_data="cmd:newtask")
    kb.adjust(3, 3)
    return kb.as_markup()


async def _keep_typing(chat_id: int):
    while True:
        await bot.send_chat_action(chat_id, "typing")
        await asyncio.sleep(4)


async def _safe_edit(msg: Message, text: str, reply_markup=None):
    """Edit message trying HTML first, fall back to plain text if it fails to parse."""
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
        return
    except TelegramBadRequest as e:
        if "parse" not in str(e).lower() and "can't" not in str(e).lower():
            return
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass


async def handle_text_internal(
    message: Message,
    text: str,
    initial_message: Message | None = None,
    uid_override: int | None = None,
):
    incoming_uid = uid_override or message.from_user.id
    print(f"[recv] uid={incoming_uid} text={text[:80]!r}", flush=True)
    history = sessions.setdefault(incoming_uid, [])

    typing_task = asyncio.create_task(_keep_typing(message.chat.id))
    placeholder = initial_message or await message.answer("<i>Thinking…</i>", parse_mode="HTML")

    accumulated = ""
    last_edit = 0.0
    new_history = None

    try:
        async for chunk, maybe_history in run_agent(text, history):
            if maybe_history is not None:
                new_history = maybe_history
                break
            accumulated += chunk
            now = time.perf_counter()
            if now - last_edit > 0.5:
                display = strip_button_marker_for_streaming(accumulated)
                if display.strip():
                    await _safe_edit(placeholder, display)
                    last_edit = now
        if accumulated.strip():
            clean_text, contextual_kb = extract_buttons(accumulated)
            keyboard = contextual_kb if contextual_kb else build_default_keyboard()
            await _safe_edit(placeholder, clean_text or "(empty response)", reply_markup=keyboard)
        else:
            await _safe_edit(placeholder, "(empty response)", reply_markup=build_default_keyboard())
    except Exception as e:
        await _safe_edit(placeholder, f"Error: {e}")
        return
    finally:
        typing_task.cancel()

    if new_history is not None:
        sessions[incoming_uid] = new_history[-20:]


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_allowed(message):
        return
    sessions[message.from_user.id] = []
    await message.answer(
        WELCOME,
        parse_mode="HTML",
        reply_markup=build_default_keyboard(),
    )


@dp.message(F.document)
async def handle_document(message: Message):
    if not is_allowed(message):
        return
    doc = message.document
    filename = doc.file_name or "document"
    suffix = Path(filename).suffix.lower()

    status = await message.answer("📎 <i>Receiving your file…</i>", parse_mode="HTML")

    local = UPLOAD_DIR / f"{uuid.uuid4()}_{filename}"
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, destination=local)

    if suffix == ".pdf":
        await status.edit_text("📎 <i>Reading the PDF…</i>", parse_mode="HTML")
        text = await extract_pdf_text(local)
        await status.edit_text("📎 <i>Summarizing…</i>", parse_mode="HTML")
        summary = await summarize_document(filename, text)
    elif suffix in (".txt", ".md"):
        text = local.read_text(errors="ignore")[:20000]
        summary = await summarize_document(filename, text)
    else:
        summary = f"File attached (type: {doc.mime_type or suffix or 'unknown'}). Content not auto-extracted."

    await _store_context(
        kind="file",
        content=f"{filename}: {summary}",
        file_path=str(local),
    )

    await status.edit_text(
        f"📎 <b>{filename}</b>\n\n{summary}\n\n<i>Stored — voice agent will reference it on calls.</i>",
        parse_mode="HTML",
        reply_markup=build_default_keyboard(),
    )


@dp.message(F.photo)
async def handle_photo(message: Message):
    if not is_allowed(message):
        return
    photo = message.photo[-1]

    status = await message.answer("🖼️ <i>Looking at the image…</i>", parse_mode="HTML")

    local = UPLOAD_DIR / f"{uuid.uuid4()}.jpg"
    file = await bot.get_file(photo.file_id)
    await bot.download_file(file.file_path, destination=local)

    description = await describe_image(local)

    caption = message.caption or ""
    content = f"Image: {description}"
    if caption:
        content = f"Image (user note: {caption}): {description}"

    await _store_context(kind="file", content=content, file_path=str(local))

    await status.edit_text(
        f"🖼️ {description}\n\n<i>Stored — voice agent will reference it on calls.</i>",
        parse_mode="HTML",
        reply_markup=build_default_keyboard(),
    )


@dp.message(F.voice | F.audio)
async def handle_voice(message: Message):
    if not is_allowed(message):
        return
    voice = message.voice or message.audio

    status = await message.answer("🎙️ <i>Transcribing…</i>", parse_mode="HTML")

    if message.voice:
        suffix = ".ogg"
    else:
        suffix = Path(voice.file_name or "audio.mp3").suffix or ".mp3"
    local = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    file = await bot.get_file(voice.file_id)
    await bot.download_file(file.file_path, destination=local)

    transcript = await transcribe_audio(local)

    if transcript.startswith("[Transcription failed"):
        await status.edit_text(transcript, parse_mode="HTML")
        return

    await status.edit_text(
        f"🎙️ <i>You said:</i> {transcript}\n\n<i>Processing…</i>",
        parse_mode="HTML",
    )

    await handle_text_internal(message, transcript, initial_message=status)


@dp.message(Command("tasks"))
async def cmd_tasks(message: Message):
    if not is_allowed(message):
        return
    await handle_text_internal(message, "Show my open tasks")


@dp.message(Command("calls"))
async def cmd_calls(message: Message):
    if not is_allowed(message):
        return
    await handle_text_internal(message, "Show my recent calls")


@dp.message(Command("contacts"))
async def cmd_contacts(message: Message):
    if not is_allowed(message):
        return
    await handle_text_internal(message, "Show my contacts")


@dp.message(Command("calendar"))
async def cmd_calendar(message: Message):
    if not is_allowed(message):
        return
    await handle_text_internal(message, "Show my calendar for this week")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_allowed(message):
        return
    await handle_text_internal(message, "What can you help me with? List capabilities briefly.")


@dp.message(F.text)
async def handle_text(message: Message):
    if not is_allowed(message):
        return
    await handle_text_internal(message, message.text)


@dp.callback_query()
async def handle_callback(cq: CallbackQuery):
    if cq.from_user.id not in ALLOWED_TELEGRAM_IDS:
        await cq.answer()
        return
    print(f"[callback] uid={cq.from_user.id} data={cq.data!r}", flush=True)

    data = cq.data or ""
    await cq.answer()

    if data in CALLBACK_PROMPTS:
        await handle_text_internal(cq.message, CALLBACK_PROMPTS[data], uid_override=cq.from_user.id)
        return

    if data == "confirm:yes":
        await handle_text_internal(
            cq.message,
            "[User clicked ✅ Yes, confirm on your previous proposal. Proceed with that exact action now.]",
            uid_override=cq.from_user.id,
        )
    elif data == "confirm:no":
        await handle_text_internal(
            cq.message,
            "[User clicked ❌ Cancel on your previous proposal. Acknowledge and don't take action.]",
            uid_override=cq.from_user.id,
        )
    elif data.startswith("task:done:"):
        task_id = data.split(":")[-1]
        await handle_text_internal(
            cq.message,
            f"[User tapped ✓ Done for task ID {task_id}. Mark it as completed and confirm.]",
            uid_override=cq.from_user.id,
        )
    elif data.startswith("event:delete:"):
        event_id = data.split(":", 2)[-1]
        await handle_text_internal(
            cq.message,
            f"[User tapped 🗑️ Delete for event ID {event_id}. Delete it and confirm.]",
            uid_override=cq.from_user.id,
        )
    elif data.startswith("book:"):
        # Format: book:TYPE:YYYY-MM-DDTHH:MM:NAME (timestamp is exactly 16 chars)
        remainder = data[len("book:"):]
        first_colon = remainder.find(":")
        if first_colon > 0 and len(remainder) >= first_colon + 1 + 17 and remainder[first_colon + 1 + 16] == ":":
            btype = remainder[:first_colon]
            after_type = remainder[first_colon + 1:]
            timestamp = after_type[:16]
            name = after_type[17:]
            synthetic = (
                f"[User chose booking slot: type={btype}, time={timestamp}, venue={name}. "
                f"Create calendar event and confirm.]"
            )
            await handle_text_internal(cq.message, synthetic, uid_override=cq.from_user.id)


async def main():
    await init_db()
    await bot.set_my_commands([
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="tasks", description="Show open tasks"),
        BotCommand(command="calls", description="Show recent calls"),
        BotCommand(command="contacts", description="Show contacts"),
        BotCommand(command="calendar", description="Show this week's calendar"),
        BotCommand(command="help", description="What I can do"),
    ])
    print("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
