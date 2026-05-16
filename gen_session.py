"""Generate a Telegram session file interactively."""
import asyncio
from telethon import TelegramClient

API_ID = 37047288
API_HASH = "f4da42cd836ec129b5ed54fbf94038b1"
SESSION_PATH = ".telegram/secretary"
PHONE = "+447490325458"


async def main():
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("Sending code request...")
        await client.send_code_request(PHONE)
        code = input("Enter the code you received on Telegram: ")
        try:
            await client.sign_in(PHONE, code)
        except Exception as e:
            if "Two-steps verification" in str(e) or "password" in str(e).lower():
                pw = input("2FA password required. Enter your password: ")
                await client.sign_in(password=pw)
            else:
                raise
    
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID: {me.id})")
    await client.disconnect()
    print(f"Session saved to {SESSION_PATH}.session")


if __name__ == "__main__":
    asyncio.run(main())
