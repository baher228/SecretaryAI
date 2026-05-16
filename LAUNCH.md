# Detailed Launch Guide

Step-by-step instructions for getting Secretary AI running with Docker.

## 1. Get API credentials

| Service | Where to get it | Required? |
|---------|----------------|-----------|
| Telegram API | [my.telegram.org](https://my.telegram.org) → API development tools | Yes |
| Gemini API | [Google AI Studio](https://aistudio.google.com/apikey) | Yes (for voice) |
| OpenAI API | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Yes (for text chat) |
| Google Calendar | Google Cloud Console → Service Accounts | Optional |
| Google Maps | Google Cloud Console → APIs & Services | Optional |

## 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```env
# Telegram MTProto (from my.telegram.org)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here

# Gemini Live voice (from Google AI Studio)
GEMINI_API_KEY=your_gemini_key_here
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_LIVE_VOICE=Zephyr
GEMINI_LIVE_ENABLED=true

# OpenAI (for text chat and agent reasoning)
OPENAI_API_KEY=sk-your-openai-key-here
OPENAI_MODEL=gpt-5.2
```

### Optional: Calendar

```env
CALENDAR_ENABLED=true
CALENDAR_ID=your_email@gmail.com
CALENDAR_SERVICE_ACCOUNT_JSON=.telegram/service_account.json
```

Place your Google service account JSON file at `.telegram/service_account.json`.

### Optional: Google Maps ETA

```env
GOOGLE_MAPS_API_KEY=your_maps_key_here
```

## 3. Start the service

```bash
docker compose up --build
```

Wait for the logs to show the server is ready. Then open:

- **Dashboard**: http://127.0.0.1:8000/dashboard
- **API docs (Swagger)**: http://127.0.0.1:8000/docs

## 4. Authenticate Telegram

Your Telegram user account needs to be linked on first run. This only needs to be done once — the session file persists in `.telegram/`.

**Send verification code:**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/telegram/auth/send-code \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890"}'
```

You'll receive a code in Telegram. Note the `phone_code_hash` from the response.

**Sign in:**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/telegram/auth/sign-in \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "code": "12345",
    "phone_code_hash": "hash_from_previous_step"
  }'
```

If your account has 2FA enabled, add `"password": "your_2fa_password"` to the request body.

**Verify authentication:**

```bash
curl http://127.0.0.1:8000/api/v1/telegram/auth/status
```

You should see `"authorized": true`.

## 5. Test a call

### Inbound calls

With the default config (`TELEGRAM_AUTO_ANSWER_INBOUND=true`), the service automatically answers incoming Telegram calls and starts the AI voice loop.

### Outbound calls

```bash
curl -X POST http://127.0.0.1:8000/api/v1/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{"target_user": "@username"}'
```

The AI live loop starts automatically (`TELEGRAM_AUTO_START_LIVE_AGENT=true`). You can also control it manually:

```bash
# Start live loop on a call
curl -X POST http://127.0.0.1:8000/api/v1/calls/{call_id}/live/start \
  -H "Content-Type: application/json" \
  -d '{"speak_response": true}'

# Check status
curl http://127.0.0.1:8000/api/v1/calls/{call_id}/live/status

# Stop live loop
curl -X POST http://127.0.0.1:8000/api/v1/calls/{call_id}/live/stop \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 6. Text chat

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What meetings do I have today?", "history": []}'
```

## 7. Docker commands

```bash
# View logs
docker compose logs -f

# Restart with rebuild
docker compose down && docker compose up --build

# Stop
docker compose down
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `TELEGRAM_API_ID` or `TELEGRAM_API_HASH` errors | Get credentials from [my.telegram.org](https://my.telegram.org) |
| Gemini voice not working | Check `GEMINI_API_KEY` is set and valid |
| Slow first STT response | Normal — Whisper model downloads on first use (fallback mode only) |
| Call connects but no AI response | Check `TELEGRAM_AUTO_START_LIVE_AGENT=true` in `.env` |
| 2FA sign-in failure | Include `"password"` field in the sign-in request |
| Calendar not working | Verify service account JSON exists and calendar is shared with the service account email |
