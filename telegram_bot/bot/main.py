import asyncio
import time
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import TELEGRAM_BOT_TOKEN, OWNER_TELEGRAM_ID
from bot.agent import run_agent
from db.session import init_db

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

sessions: dict[int, list] = {}


def is_owner(message: Message) -> bool:
    return message.from_user.id == OWNER_TELEGRAM_ID


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_owner(message):
        return
    sessions[message.from_user.id] = []
    await message.answer("Ready. Ask about your calls or tasks.")


async def _keep_typing(chat_id: int):
    while True:
        await bot.send_chat_action(chat_id, "typing")
        await asyncio.sleep(4)


@dp.message(F.text)
async def handle_text(message: Message):
    if not is_owner(message):
        return
    uid = message.from_user.id
    history = sessions.setdefault(uid, [])

    typing_task = asyncio.create_task(_keep_typing(message.chat.id))
    placeholder = await message.answer("…")

    accumulated = ""
    last_edit = 0.0
    new_history = None

    try:
        async for chunk, maybe_history in run_agent(message.text, history):
            if maybe_history is not None:
                new_history = maybe_history
                break
            accumulated += chunk
            now = time.perf_counter()
            if now - last_edit > 0.5 and accumulated.strip():
                try:
                    await placeholder.edit_text(accumulated)
                    last_edit = now
                except Exception:
                    pass
        if accumulated.strip():
            try:
                await placeholder.edit_text(accumulated)
            except Exception:
                pass
        else:
            await placeholder.edit_text("(empty response)")
    except Exception as e:
        await placeholder.edit_text(f"Error: {e}")
        return
    finally:
        typing_task.cancel()

    if new_history is not None:
        sessions[uid] = new_history[-20:]


async def main():
    await init_db()
    print("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
