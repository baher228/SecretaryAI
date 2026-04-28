# Secretary AI

AI-powered phone secretary that handles Telegram voice calls autonomously. Uses **Gemini 3.1 Flash Live** for real-time audio-to-audio conversation, with Z.AI GLM for text chat and agent reasoning.

## Features

- **Voice calls** — Gemini Live streams call audio directly to/from the AI model (no separate STT/TTS needed)
- **Fallback pipeline** — STT (Whisper) → Z.AI GLM → TTS (Edge TTS) when Gemini Live is disabled
- **Text chat** — Z.AI GLM-powered conversational assistant via REST API
- **Google Calendar** — reads events, queues scheduling requests, processes them via AI
- **Proactive reminders** — calls you before upcoming calendar events
- **Auto-answer** — picks up inbound Telegram calls and starts the AI loop
- **Auto-greeting** — plays a configurable greeting when a call connects
- **Dashboard** — web UI for testing calls, auth, and live WebSocket interactions

## Prerequisites

- **Docker** and **Docker Compose**
- **Telegram API credentials** — get `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org)
- **Gemini API key** — get one from [Google AI Studio](https://aistudio.google.com/apikey)
- **Z.AI API key** — for text chat and agent reasoning
- **Google Calendar** (optional) — service account JSON for calendar integration
- **Google Maps API key** (optional) — for ETA/distance lookups

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials. The required ones are:

```env
# Telegram (required for calls)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash

# Gemini Live (required for voice)
GEMINI_API_KEY=your_gemini_key

# Z.AI (required for text chat / agent reasoning)
ZAI_API_KEY=your_zai_key
```

See `.env.example` for all available settings and their defaults.

### 2. Start the service

```bash
docker compose up --build
```

The service starts at:
- **Dashboard**: http://127.0.0.1:8000/dashboard
- **API docs**: http://127.0.0.1:8000/docs

### 3. Authenticate Telegram

On first run, you need to link your Telegram account:

```bash
# Send verification code
curl -X POST http://127.0.0.1:8000/api/v1/telegram/auth/send-code \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890"}'

# Sign in with the code (use phone_code_hash from the response above)
curl -X POST http://127.0.0.1:8000/api/v1/telegram/auth/sign-in \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890", "code": "12345", "phone_code_hash": "from_previous_step"}'

# If your account has 2FA, include "password": "your_2fa_password"

# Verify
curl http://127.0.0.1:8000/api/v1/telegram/auth/status
```

The session persists in `.telegram/secretary.session` — you only need to do this once.

### 4. Make a call

Once authenticated, inbound calls are auto-answered by default. To make an outbound call:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{"target_user": "@username"}'
```

The AI live loop starts automatically on the call.

## Voice Modes

| Mode | When | How it works |
|------|------|-------------|
| **Gemini Live** (default) | `GEMINI_API_KEY` set + `GEMINI_LIVE_ENABLED=true` | Audio streams directly to Gemini 3.1 Flash Live via WebSocket — lowest latency |
| **STT → Z.AI → TTS** | Gemini disabled or key missing | Whisper transcribes audio → Z.AI generates reply → Edge TTS synthesizes speech |

## Calendar Integration (Optional)

1. Create a Google Cloud service account with Calendar API access
2. Share your calendar with the service account email
3. Configure in `.env`:

```env
CALENDAR_ENABLED=true
CALENDAR_ID=your_email@gmail.com
CALENDAR_SERVICE_ACCOUNT_JSON=.telegram/service_account.json
```

The AI can then check availability, schedule meetings, and send reminders.

## API Endpoints

| Category | Endpoint | Description |
|----------|----------|-------------|
| Health | `GET /api/v1/health` | Service health check |
| Auth | `POST /api/v1/telegram/auth/send-code` | Send Telegram login code |
| Auth | `POST /api/v1/telegram/auth/sign-in` | Sign in to Telegram |
| Auth | `GET /api/v1/telegram/auth/status` | Check auth status |
| Calls | `POST /api/v1/calls/outbound` | Start outbound call |
| Calls | `POST /api/v1/calls/{id}/hangup` | Hang up a call |
| Calls | `GET /api/v1/calls` | List active calls |
| Live | `POST /api/v1/calls/{id}/live/start` | Start AI live loop on a call |
| Live | `POST /api/v1/calls/{id}/live/stop` | Stop AI live loop |
| Live | `GET /api/v1/calls/{id}/live/status` | Live loop status |
| Agent | `POST /api/v1/agent/reply` | Get AI reply for a transcript |
| Agent | `POST /api/v1/agent/analyze` | Structured intent analysis |
| Agent | `POST /api/v1/agent/live/respond` | Full live response (AI + TTS + play) |
| Chat | `POST /api/v1/chat` | Text chat with Z.AI |
| Calendar | `POST /api/v1/calendar/queue` | Queue a calendar operation |
| Calendar | `GET /api/v1/calendar/cache` | Get cached calendar events |
| WebSocket | `WS /api/v1/ws/live/{id}` | Real-time transcript ↔ AI loop |

## Project Structure

```
src/secretary_ai/
├── core/
│   └── config.py          # Settings (from .env)
├── services/
│   ├── secretary.py       # Main orchestrator
│   ├── gemini_live.py     # Gemini Live audio-to-audio bridge
│   ├── ai_agent.py        # Z.AI agent reasoning
│   ├── zai_client.py      # Shared Z.AI HTTP client
│   ├── telegram_calls.py  # Telegram MTProto call adapter
│   ├── stt.py             # Speech-to-text (Whisper)
│   ├── tts.py             # Text-to-speech (Edge TTS)
│   ├── calendar.py        # Google Calendar service
│   ├── memory_store.py    # Call context memory
│   ├── maps.py            # Google Maps ETA
│   └── booking.py         # Booking service
├── domain/
│   └── models.py          # Pydantic request/response models
├── api/
│   └── routes.py          # FastAPI endpoints
└── main.py                # App entrypoint
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -q

# Lint
ruff check src/

# Run locally (without Docker)
uvicorn secretary_ai.main:app --host 0.0.0.0 --port 8000 --app-dir src
```

## Stack

- **FastAPI** — REST API framework
- **Telethon** — Telegram MTProto client (user account)
- **py-tgcalls** — Telegram call/media layer
- **google-genai** — Gemini 3.1 Flash Live API
- **Z.AI GLM** — Text chat and agent reasoning
- **faster-whisper** — Local STT (fallback)
- **edge-tts** — TTS synthesis (fallback)
- **Google Calendar API** — Calendar integration
