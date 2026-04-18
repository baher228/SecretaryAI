# Secretary AI (Scaffold)

This repository is intentionally initialized as architecture only.
Core business logic and external integrations are not implemented yet.

## Current scope

- Folder structure and module boundaries.
- API contracts (request/response models).
- Route skeletons for inbound/outbound/post-call workflows.
- A service layer interface (`SecretaryService`) with TODO methods.
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
  secretary.py
  main.py
tests/
```

## Quick start

```bash
python -m venv .venv
. .venv/Scripts/activate  # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
uvicorn secretary_ai.main:app --reload
```

## Endpoints

- `GET /api/v1/health` - service health + scaffold mode
- `GET /api/v1/architecture` - architecture summary
- `POST /api/v1/calls/inbound` - placeholder (`501`)
- `POST /api/v1/calls/outbound` - placeholder (`501`)
- `POST /api/v1/calls/post-call` - placeholder (`501`)
- `GET /api/v1/calls/{call_id}` - placeholder (`501`)

## Next implementation steps

1. Implement intent classification contract.
2. Add telephony adapter (inbound/outbound + transfer/voicemail).
3. Add calendar adapter (book/reschedule/cancel).
4. Add summary dispatcher (Telegram/email/CRM).
5. Add persistence for calls and actions.
