# Launch Guide (Telegram MTProto + Docker)

## 1. Configure environment

```powershell
Copy-Item .env.example .env
```

Update `.env`:

```env
ZAI_API_KEY=your_real_zai_key
ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
ZAI_MODEL=glm-5.1
AGENT_MAX_TOKENS=160
AGENT_HISTORY_TURNS=4

TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_SESSION_PATH=.telegram/secretary
TELEGRAM_AUTO_ANSWER_INBOUND=true
TELEGRAM_AUTO_START_LIVE_AGENT=true
TELEGRAM_AUTO_START_LIVE_SPEAK_RESPONSE=true
TELEGRAM_AUTO_START_SCAN_SECONDS=2.0
TELEGRAM_AUDIO_ROOT=.telegram/audio
ASSISTANT_AUTO_GREET_ON_CONNECT=true
ASSISTANT_GREETING_MESSAGE=Hello, this is your AI secretary. How can I help you today?
TTS_ENABLED=true
TTS_PROVIDER=edge_tts
TTS_VOICE=en-US-AriaNeural
TTS_RATE=+0%
TTS_VOLUME=+0%
STT_ENABLED=true
STT_PROVIDER=faster_whisper
STT_MODEL=tiny.en
STT_LANGUAGE=en
STT_DEVICE=cpu
STT_COMPUTE_TYPE=int8
STT_MIN_CHARS=6
STT_RECENT_ONLY=true
STT_TAIL_SECONDS=5.0
STT_MIN_NEW_BYTES=12000
TELEGRAM_LIVE_POLL_SECONDS=1.2
TELEGRAM_LIVE_TTS_COOLDOWN_SECONDS=2.5
```

`TELEGRAM_API_ID` and `TELEGRAM_API_HASH` come from `my.telegram.org`.

## 2. Start container

```powershell
docker compose up --build
```

App URLs:

- `http://127.0.0.1:8000/dashboard`
- `http://127.0.0.1:8000/docs`

## 3. Authenticate Telegram user session

1. Send code:

```powershell
$body = @{ phone_number = "+441234567890" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/telegram/auth/send-code" `
  -ContentType "application/json" `
  -Body $body
```

2. Sign in (use returned `phone_code_hash`):

```powershell
$body = @{
  phone_number = "+441234567890"
  code = "12345"
  phone_code_hash = "from_send_code"
  password = $null
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/telegram/auth/sign-in" `
  -ContentType "application/json" `
  -Body $body
```

If your account has 2FA, call sign-in with `password` set.

3. Confirm status:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/telegram/auth/status"
```

## 4. Start outbound call

```powershell
$body = @{
  target_user = "@target_username"
  purpose = "reminder"
  initial_audio_path = $null
  metadata = @{}
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/calls/outbound" `
  -ContentType "application/json" `
  -Body $body
```

## 5. Push transcript and get AI response

```powershell
$body = @{
  call_id = "tg-123456789"
  transcript = "Caller asked to reschedule to tomorrow at 3 PM."
  context = @{}
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/agent/reply" `
  -ContentType "application/json" `
  -Body $body
```

Structured analysis endpoint (intent + confidence + transfer flag):

```powershell
$body = @{
  call_id = "tg-123456789"
  transcript = "Please reschedule my appointment to Tuesday at 3 PM."
  context = @{ customer_name = "Alex" }
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/agent/analyze" `
  -ContentType "application/json" `
  -Body $body
```

Near realtime talk loop endpoint (transcript -> AI -> TTS -> call):

```powershell
$body = @{
  call_id = "tg-123456789"
  transcript = "Could we move this appointment to Thursday morning?"
  context = @{ source = "dashboard" }
  speak_response = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/agent/live/respond" `
  -ContentType "application/json" `
  -Body $body
```

Telegram-native live loop (no dashboard mic required):

By default this starts automatically when a call becomes active.

Manual control is still available:

1. Start outbound call and capture `call_id`.
2. Start live loop manually:

```powershell
$callId = "tg-123456789"
$body = @{
  context = @{ source = "telegram_live" }
  speak_response = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/calls/$callId/live/start" `
  -ContentType "application/json" `
  -Body $body
```

3. Check status:

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/api/v1/calls/$callId/live/status"
```

4. Stop live loop:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/calls/$callId/live/stop" `
  -ContentType "application/json" `
  -Body "{}"
```

Note: first `live/start` can be slower because Whisper model files are downloaded.

WebSocket realtime loop (persistent connection):

- Open `http://127.0.0.1:8000/dashboard`
- Go to `API Lab & Debug`
- Use the `WS /api/v1/ws/live/{call_id}` card:
  - connect using your active `call_id` (example: `tg-123456789`),
  - send transcript chunks manually or click `Start Live Mic` for continuous browser speech capture,
  - inspect returned `agent_response` events (includes `reply`, `intent`, `tts_status`, `call_audio_status`).
- Use the `POST /api/v1/calls/{call_id}/live/start` dashboard card for Telegram-native speech loop.

## 6. Useful Docker commands

Logs:

```powershell
docker compose logs -f
```

Restart with rebuild:

```powershell
docker compose down
docker compose up --build
```

Stop:

```powershell
docker compose down
```
