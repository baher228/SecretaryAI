# Secretary AI (Scaffold)

This repository is intentionally initialized as architecture only.
Core business logic and external integrations are not implemented yet.
Model connectivity check for Z.AI GLM is implemented.

## Current scope

- Folder structure and module boundaries.
- API contracts (request/response models).
- Route skeletons for inbound/outbound/post-call workflows.
- A service layer interface (`SecretaryService`) with TODO methods.
- A working Z.AI GLM connectivity check endpoint.
- Architecture endpoint for quick project orientation.

## Architecture

1. `API Layer` receives requests and exposes contracts.
2. `SecretaryService` is the orchestrator boundary.
3. `Adapters` (planned): telephony, intent, calendar, notifications, storage.

## Project layout

```text
src/secretary_ai/
  api/routes.py
  core/config.py
  domain/models.py
  services/secretary.py
  main.py
tests/
```

## Quick start (Docker)

```bash
copy .env.example .env
docker compose up --build
```

Detailed run instructions: [LAUNCH.md](./LAUNCH.md)

## Endpoints

- `GET /api/v1/health` - service health + scaffold mode
- `GET /api/v1/architecture` - architecture summary
- `POST /api/v1/model/check` - verify Z.AI GLM API connectivity
- `POST /api/v1/calls/inbound` - placeholder (`501`)
- `POST /api/v1/calls/outbound` - placeholder (`501`)
- `POST /api/v1/calls/post-call` - placeholder (`501`)
- `GET /api/v1/calls/{call_id}` - placeholder (`501`)

## Connect Z.AI GLM

1. Add your key in `.env`:
   `ZAI_API_KEY=...`
2. Keep defaults or change model/base URL:
   `ZAI_MODEL=glm-5.1`
   `ZAI_BASE_URL=https://api.z.ai/api/paas/v4`
3. Start API:
   `uvicorn secretary_ai.main:app --reload`
4. Test connection:
   `POST /api/v1/model/check`
   body: `{"prompt":"Reply with connection_ok"}`

## Next implementation steps

1. Implement intent classification contract.
2. Add telephony adapter (inbound/outbound + transfer/voicemail).
3. Add calendar adapter (book/reschedule/cancel).
4. Add summary dispatcher (Telegram/email/CRM).
5. Add persistence for calls and actions.
