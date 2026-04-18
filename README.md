# Secretary AI (Telegram MTProto MVP)

Experimental Python backend for a hackathon AI secretary using a real Telegram user account (MTProto), not the Bot API.

## What it does now

- Telegram user-session auth (`send-code`, `sign-in`, persisted session file).
- Outbound private Telegram call trigger.
- Inbound private call state capture (and optional auto-answer).
- Call event store for state tracking.
- Best-effort audio tools:
  - stream local audio file into a call,
  - record incoming call audio to file.
- Local API for your main AI agent:
  - push transcript snippets,
  - request AI reply + action items from Z.AI GLM.
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
- `POST /api/v1/calls/{call_id}/transcript`
- `POST /api/v1/calls/post-call`
- `GET /api/v1/calls`
- `GET /api/v1/calls/{call_id}`
- `GET /api/v1/calls/events`

Agent reasoning:

- `POST /api/v1/agent/reply`

## Notes

- This is experimental infrastructure, not production telecom.
- Telegram call behavior may vary by account/region/client constraints.
- Keep this provider behind an adapter so you can swap back to Twilio/other vendors later.
