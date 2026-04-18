# Launch Guide (Docker)

This guide explains how to run `Secretary AI` in a Docker container.

## 1. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Open `.env` and set at least:

```env
ZAI_API_KEY=your_real_key_here
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
ZAI_MODEL=glm-5.1
```

If you are on GLM Coding Plan, use:

```env
ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
```

## 2. Build and start container

```powershell
docker compose up --build
```

Server endpoint:

`http://127.0.0.1:8000`

## 3. Verify service health

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/health"
```

## 4. Verify GLM connection

```powershell
$body = @{ prompt = "Reply with connection_ok" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/model/check" `
  -ContentType "application/json" `
  -Body $body
```

Expected response includes:

- `"provider": "z.ai"`
- `"connected": true` (if key/base URL/model are correct)

## 5. Useful Docker commands

View logs:

```powershell
docker compose logs -f
```

Run in background:

```powershell
docker compose up --build -d
```

Stop container:

```powershell
docker compose down
```
