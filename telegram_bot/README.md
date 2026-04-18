# Secretary Telegram Bot

AI secretary bot using Z.AI GLM-5.1 with tool calling over a local SQLite database.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN, OWNER_TELEGRAM_ID, ZAI_API_KEY
python -m scripts.seed   # optional: populate mock data
python -m bot.main
```

## Test

Send `/start` to your bot in Telegram, then:
- "What calls did I have recently?"
- "What are my open tasks?"
- "Remind me to call Paul tomorrow"
