import asyncio
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


@dp.message(F.text)
async def handle_text(message: Message):
    if not is_owner(message):
        return
    uid = message.from_user.id
    history = sessions.setdefault(uid, [])
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        reply, new_history = await run_agent(message.text, history)
    except Exception as e:
        await message.answer(f"Error: {e}")
        return
    sessions[uid] = new_history[-20:]
    await message.answer(reply or "(empty response)")


async def main():
    await init_db()
    print("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
