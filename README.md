# Secretary AI (Telegram MTProto MVP)

Experimental Python backend for a hackathon AI secretary using a real Telegram user account (MTProto), not the Bot API.

## What it does now

- Telegram user-session auth (`send-code`, `sign-in`, persisted session file).
- Outbound private Telegram call trigger.
- Auto-greeting playback on outbound call connect.
- Inbound private call state capture (and optional auto-answer).
- Call event store for state tracking.
- Best-effort audio tools:
  - stream local audio file into a call,
  - record incoming call audio to file.
- Local API for your main AI agent:
  - push transcript snippets,
  - request AI reply + action items from Z.AI GLM,
  - request structured AI analysis (intent/confidence/handoff/action plan),
  - run a near realtime talk loop (transcript -> AI -> TTS -> call audio out).
- Dashboard for manual testing and hackathon demos.

## Stack

- FastAPI
- Telethon (MTProto user account)
- py-tgcalls (Telegram call/media layer)
- Z.AI GLM (`https://api.z.ai/api/coding/paas/v4`)

## Quick start

```bash
copy .env.example .env
docker compose up --build
```

- Dashboard: `http://127.0.0.1:8000/dashboard`
- Swagger: `http://127.0.0.1:8000/docs`

Detailed launch guide: [LAUNCH.md](./LAUNCH.md)

## API overview

- `GET /api/v1/health`
- `GET /api/v1/architecture`
- `POST /api/v1/model/check`

Telegram auth:

- `GET /api/v1/telegram/auth/status`
- `POST /api/v1/telegram/auth/send-code`
- `POST /api/v1/telegram/auth/sign-in`

Calls:

- `POST /api/v1/calls/outbound`
- `POST /api/v1/calls/{call_id}/hangup`
- `POST /api/v1/calls/{call_id}/audio/play`
- `POST /api/v1/calls/{call_id}/audio/record`
- `POST /api/v1/calls/{call_id}/live/start` (Telegram-native full loop)
- `POST /api/v1/calls/{call_id}/live/stop`
- `GET /api/v1/calls/{call_id}/live/status`
- `POST /api/v1/calls/{call_id}/transcript`
- `POST /api/v1/calls/post-call`
- `GET /api/v1/calls`
- `GET /api/v1/calls/{call_id}`
- `GET /api/v1/calls/events`

Agent reasoning:

- `POST /api/v1/agent/reply`
- `POST /api/v1/agent/analyze`
- `POST /api/v1/agent/live/respond`
- `WS /api/v1/ws/live/{call_id}` (realtime transcript -> AI -> optional TTS/call streaming)

## Notes

- This is experimental infrastructure, not production telecom.
- Telegram call behavior may vary by account/region/client constraints.
- Keep this provider behind an adapter so you can swap back to Twilio/other vendors later.
- Live conversation currently uses browser speech-to-text + server TTS + Telegram audio streaming.
- Telegram-native live loop is now available: call audio recording -> STT -> AI -> TTS response in call.
- Telegram-native live loop auto-starts by default on active calls (`TELEGRAM_AUTO_START_LIVE_AGENT=true`).
- First Telegram live loop run downloads the Whisper model (`STT_MODEL`) and may take extra time.
- For immediate first speech, configure `ASSISTANT_AUTO_GREET_ON_CONNECT` and `ASSISTANT_GREETING_MESSAGE`.
- Dashboard includes a WebSocket live test card for persistent two-way turn handling.
- Dashboard live card supports continuous browser mic capture (`Start Live Mic`) and auto-streams finalized transcript chunks over WS.
