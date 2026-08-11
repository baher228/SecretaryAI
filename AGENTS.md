# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Secretary AI is an AI-powered phone secretary with two independent products in one repo:

1. **Secretary AI Voice Service** (`src/secretary_ai/`) — FastAPI app (port 8000) handling Telegram voice calls via Gemini Live, text chat via Z.AI GLM, and Google Calendar integration.
2. **Secretary Telegram Bot** (`telegram_bot/`) — standalone `aiogram` bot with SQLite, independent dependencies.

No shared code between the two products at runtime.

### Running the main service (without Docker)

```bash
PYTHONPATH=src uvicorn secretary_ai.main:app --host 0.0.0.0 --port 8000 --app-dir src
```

Dashboard: http://127.0.0.1:8000/dashboard  
API docs: http://127.0.0.1:8000/docs

### Lint & test

See `README.md` "Development" section. Key commands:

- **Lint:** `ruff check src/`
- **Tests:** `pytest tests/ -q` (runs 48 tests; all pass without external API keys)
- Ensure `~/.local/bin` is on `PATH` for `ruff` / `pytest` executables.

### .env gotcha for tests

The `.env.example` ships `TELEGRAM_API_ID=` (empty string). Pydantic-settings tries to parse this as `int` and fails. When running tests from the project root, either:
- Comment out `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in `.env`, or
- Run tests from a directory without a `.env` file (e.g., `cd /tmp && PYTHONPATH=/workspace/src pytest /workspace/tests/`).

### External API keys

All API keys (`ZAI_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`, etc.) are optional at the Settings level. The app starts and serves the health endpoint, dashboard, and most REST endpoints without them. Chat and voice features require their respective keys.

### Telegram Bot (secondary product)

```bash
cd telegram_bot && pip install -e . && python -m bot.main
```

Requires `TELEGRAM_BOT_TOKEN`, `ZAI_API_KEY`, and `TAVILY_API_KEY` in `telegram_bot/.env`.
