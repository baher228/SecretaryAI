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

TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_SESSION_PATH=.telegram/secretary
TELEGRAM_AUTO_ANSWER_INBOUND=true
TELEGRAM_AUDIO_ROOT=.telegram/audio
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
