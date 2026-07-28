import asyncio
import secrets
import warnings
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from google import genai
from pydantic import BaseModel, Field

from secretary_ai.services.secretary import SecretaryService

router = APIRouter(include_in_schema=False)

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver"}
_NO_STORE = {"Cache-Control": "no-store"}
_STATIC_HEADERS = {"Cache-Control": "public, max-age=3600"}
_PAGE_HEADERS = {
    **_NO_STORE,
    "Content-Security-Policy": (
        "default-src 'self'; "
        "connect-src 'self' wss://generativelanguage.googleapis.com; "
        "img-src 'self'; style-src 'self'; script-src 'self'; worker-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def _secretary(request: Request) -> SecretaryService:
    return request.app.state.secretary  # type: ignore[no-any-return]


def _require_access(
    request: Request,
    secretary: SecretaryService = Depends(_secretary),
    x_voice_app_key: str | None = Header(default=None),
) -> SecretaryService:
    expected = secretary.settings.voice_app_access_key
    if expected:
        if not x_voice_app_key or not secrets.compare_digest(x_voice_app_key, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Enter the voice app access key.",
            )
        return secretary

    host = request.url.hostname or ""
    if host not in _LOCAL_HOSTS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set VOICE_APP_ACCESS_KEY on the server before using the voice app remotely.",
        )
    return secretary


class VoiceActionRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    request: str = Field(min_length=2, max_length=2000)


@router.get("/voice")
async def voice_redirect() -> RedirectResponse:
    return RedirectResponse("/voice/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/voice/", response_class=HTMLResponse)
async def voice_app() -> HTMLResponse:
    return HTMLResponse(VOICE_HTML, headers=_PAGE_HEADERS)


@router.get("/voice/app.css")
async def voice_css() -> Response:
    return Response(VOICE_CSS, media_type="text/css", headers=_STATIC_HEADERS)


@router.get("/voice/app.js")
async def voice_js() -> Response:
    return Response(VOICE_JS, media_type="application/javascript", headers=_STATIC_HEADERS)


@router.get("/voice/audio-worklet.js")
async def voice_worklet() -> Response:
    return Response(AUDIO_WORKLET_JS, media_type="application/javascript", headers=_STATIC_HEADERS)


@router.get("/voice/sw.js")
async def voice_service_worker() -> Response:
    return Response(
        SERVICE_WORKER_JS,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/voice/"},
    )


@router.get("/voice/manifest.webmanifest")
async def voice_manifest() -> JSONResponse:
    return JSONResponse(VOICE_MANIFEST, media_type="application/manifest+json", headers=_STATIC_HEADERS)


@router.get("/voice/icon.svg")
async def voice_icon() -> Response:
    return Response(VOICE_ICON, media_type="image/svg+xml", headers=_STATIC_HEADERS)


@router.post("/api/v1/voice/session-token")
async def voice_session_token(
    secretary: SecretaryService = Depends(_require_access),
) -> JSONResponse:
    settings = secretary.settings
    if not settings.gemini_live_enabled or not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini Live is not configured on the server.",
        )

    now = datetime.now(timezone.utc)

    def create_token() -> str:
        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options={"api_version": settings.gemini_live_api_version},
        )
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="The SDK's token creation implementation is experimental",
                )
                token = client.auth_tokens.create(
                    config={
                        "uses": 1,
                        "expire_time": now + timedelta(minutes=20),
                        "new_session_expire_time": now + timedelta(minutes=1),
                        "live_connect_constraints": {
                            "model": settings.gemini_live_model,
                            "config": {"response_modalities": ["AUDIO"]},
                        },
                    }
                )
            if not token.name:
                raise RuntimeError("Gemini returned an empty session token.")
            return token.name
        finally:
            client.close()

    try:
        token = await asyncio.to_thread(create_token)
    except Exception as exc:
        code = getattr(exc, "code", None)
        detail = (
            "Gemini rejected the server API key. Replace GEMINI_API_KEY and try again."
            if code in {401, 403}
            else "Gemini could not start a voice session. Try again."
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc

    api_version = settings.gemini_live_api_version
    websocket_url = (
        "wss://generativelanguage.googleapis.com/ws/"
        f"google.ai.generativelanguage.{api_version}."
        "GenerativeService.BidiGenerateContentConstrained"
    )
    return JSONResponse(
        {
            "token": token,
            "model": settings.gemini_live_model,
            "voice": settings.gemini_live_voice,
            "language": settings.language,
            "websocket_url": websocket_url,
        },
        headers=_NO_STORE,
    )


@router.post("/api/v1/voice/action")
async def voice_action(
    payload: VoiceActionRequest,
    secretary: SecretaryService = Depends(_require_access),
) -> JSONResponse:
    result = await secretary.live_agent_respond(
        call_id=payload.call_id,
        transcript=payload.request.strip(),
        context={"source": "voice_app"},
        speak_response=False,
    )
    return JSONResponse(
        {
            "reply": result.reply,
            "intent": result.intent.value,
            "action_items": result.action_items,
            "requires_human": result.requires_human,
        },
        headers=_NO_STORE,
    )


VOICE_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#09090b">
    <meta name="description" content="Low-latency voice access to Secretary AI.">
    <title>Secretary</title>
    <link rel="manifest" href="/voice/manifest.webmanifest?v=3">
    <link rel="icon" href="/voice/icon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="/voice/app.css?v=3">
    <script src="/voice/app.js?v=3" defer></script>
  </head>
  <body>
    <a class="skip-link" href="#voice-main">Skip to voice controls</a>
    <main id="voice-main" class="voice-shell">
      <header class="app-header">
        <h1>Secretary</h1>
        <p class="connection-status" id="connection-status">
          <span class="status-dot" aria-hidden="true"></span>
          <span id="connection-label">Ready</span>
        </p>
      </header>

      <section class="conversation" aria-labelledby="voice-state">
        <div class="audio-meter" id="audio-meter" aria-hidden="true">
          <i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i>
          <i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i>
        </div>
        <h2 id="voice-state">Ready</h2>
        <p class="state-detail" id="state-detail">Tap Start to begin.</p>
      </section>

      <section class="current-transcript" aria-label="Latest transcript">
        <p id="latest-transcript">Your latest words will appear here.</p>
      </section>

      <p class="sr-only" id="announcer" aria-live="polite" aria-atomic="true"></p>

      <nav class="call-controls" aria-label="Call controls">
        <button class="control-button secondary-control" id="mute-button" type="button" aria-pressed="false" disabled>
          <span class="control-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 5.1 2.1M15 10V5a3 3 0 0 0-.2-1M5 10v1a7 7 0 0 0 11.9 5M19 10v1a7 7 0 0 1-.6 2.8M12 18v4M8 22h8M3 3l18 18"/></svg>
          </span>
          <span>Mute</span>
        </button>

        <button class="control-button primary-control" id="call-button" type="button">
          <span class="control-icon" aria-hidden="true">
            <svg class="phone-start" viewBox="0 0 24 24"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.4 19.4 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.8a2 2 0 0 1-.5 2.1L8.1 9.8a16 16 0 0 0 6 6l1.2-1.2a2 2 0 0 1 2.1-.5 12.7 12.7 0 0 0 2.8.7 2 2 0 0 1 1.8 2.1Z"/></svg>
            <svg class="phone-end" viewBox="0 0 24 24"><path d="M3.6 15.2a15.5 15.5 0 0 1 16.8 0l1.1-2.4a2 2 0 0 0-.8-2.5 18.7 18.7 0 0 0-17.4 0 2 2 0 0 0-.8 2.5l1.1 2.4Z"/></svg>
          </span>
          <span id="call-label">Start</span>
        </button>

        <button class="control-button secondary-control" id="transcript-button" type="button" aria-haspopup="dialog" aria-controls="transcript-dialog">
          <span class="control-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8ZM8 8h8M8 12h6"/></svg>
          </span>
          <span>Transcript</span>
        </button>
      </nav>
    </main>

    <dialog id="transcript-dialog" aria-labelledby="transcript-title">
      <div class="dialog-header">
        <div>
          <h2 id="transcript-title">Transcript</h2>
          <p>Only this session appears here.</p>
        </div>
        <button class="icon-button" id="close-transcript" type="button" aria-label="Close transcript">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>
        </button>
      </div>
      <ol class="transcript-list" id="transcript-list">
        <li class="empty-transcript">Start a conversation to see the transcript.</li>
      </ol>
    </dialog>

    <dialog id="access-dialog" aria-labelledby="access-title" aria-describedby="access-help">
      <form method="dialog" id="access-form">
        <h2 id="access-title">Connect to your secretary</h2>
        <p id="access-help">Enter the access key configured on your server.</p>
        <label for="access-key">Access key</label>
        <input id="access-key" name="access-key" type="password" autocomplete="current-password" aria-describedby="access-help access-error" required>
        <p class="form-error" id="access-error" role="alert"></p>
        <div class="dialog-actions">
          <button class="text-button" value="cancel" type="button" id="cancel-access">Not now</button>
          <button class="submit-button" value="default" type="submit">Connect</button>
        </div>
      </form>
    </dialog>

    <noscript>Secretary needs JavaScript for real-time audio.</noscript>
  </body>
</html>
"""


VOICE_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #09090b;
  --surface: #18181b;
  --surface-strong: #27272a;
  --ink: #f0fdf4;
  --muted: #b4b4bd;
  --line: #34343a;
  --active: #10b981;
  --danger: #ef4444;
  --focus: #6ee7b7;
  --space-xs: 0.5rem;
  --space-sm: 0.75rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;
  --space-2xl: 3rem;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-synthesis: none;
  font-kerning: normal;
}

* { box-sizing: border-box; }

html {
  min-height: 100%;
  background: var(--bg);
}

body {
  min-width: 20rem;
  min-height: 100vh;
  min-height: 100svh;
  margin: 0;
  color: var(--ink);
  background: var(--bg);
  font-size: 1rem;
  line-height: 1.55;
  letter-spacing: 0.01em;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

button,
input {
  font: inherit;
}

button {
  color: inherit;
  -webkit-tap-highlight-color: transparent;
}

button:focus-visible,
input:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 3px;
}

.skip-link {
  position: fixed;
  z-index: 30;
  top: var(--space-sm);
  left: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  color: #04130e;
  background: var(--focus);
  border-radius: 0.5rem;
  transform: translateY(-150%);
}

.skip-link:focus { transform: translateY(0); }

.voice-shell {
  width: min(100%, 42rem);
  min-height: 100vh;
  min-height: 100svh;
  margin: 0 auto;
  padding:
    max(1.5rem, env(safe-area-inset-top))
    max(1.5rem, env(safe-area-inset-right))
    max(1.25rem, env(safe-area-inset-bottom))
    max(1.5rem, env(safe-area-inset-left));
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.app-header h1 {
  margin: 0;
  font-size: 1.75rem;
  line-height: 1.2;
  letter-spacing: -0.025em;
  font-weight: 650;
  text-wrap: balance;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  min-height: 1.75rem;
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
  font-variant-numeric: tabular-nums;
}

.status-dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--muted);
  transition: background-color 180ms var(--ease), transform 180ms var(--ease);
}

body[data-state="listening"] .connection-status,
body[data-state="speaking"] .connection-status,
body[data-state="thinking"] .connection-status {
  color: var(--active);
}

body[data-state="listening"] .status-dot,
body[data-state="speaking"] .status-dot,
body[data-state="thinking"] .status-dot {
  background: var(--active);
  transform: scale(1.08);
}

body[data-state="error"] .connection-status { color: #fca5a5; }
body[data-state="error"] .status-dot { background: var(--danger); }

.conversation {
  flex: 1 1 auto;
  min-height: 23rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: var(--space-xl) 0;
  text-align: center;
}

.audio-meter {
  width: min(100%, 29rem);
  height: 8rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: clamp(0.3rem, 1.8vw, 0.75rem);
  color: var(--muted);
}

.audio-meter i {
  display: block;
  width: clamp(0.18rem, 0.8vw, 0.38rem);
  height: 3.5rem;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.45;
  transform: scaleY(0.08);
  transform-origin: center;
  transition: color 180ms var(--ease), opacity 180ms var(--ease);
}

.audio-meter i:nth-child(2),
.audio-meter i:nth-last-child(2) { --meter-height: 0.2; }
.audio-meter i:nth-child(3),
.audio-meter i:nth-last-child(3) { --meter-height: 0.32; }
.audio-meter i:nth-child(4),
.audio-meter i:nth-last-child(4) { --meter-height: 0.48; }
.audio-meter i:nth-child(5),
.audio-meter i:nth-last-child(5) { --meter-height: 0.68; }
.audio-meter i:nth-child(6),
.audio-meter i:nth-last-child(6) { --meter-height: 0.92; }
.audio-meter i:nth-child(7),
.audio-meter i:nth-last-child(7) { --meter-height: 0.58; }
.audio-meter i:nth-child(8),
.audio-meter i:nth-last-child(8) { --meter-height: 1.15; }
.audio-meter i:nth-child(9) { --meter-height: 1.45; }

body[data-state="listening"] .audio-meter,
body[data-state="speaking"] .audio-meter {
  color: var(--active);
}

body[data-state="listening"] .audio-meter i,
body[data-state="speaking"] .audio-meter i {
  opacity: 1;
  animation: meter 900ms ease-in-out infinite alternate;
  animation-delay: calc(var(--meter-index, 0) * -65ms);
}

.audio-meter i:nth-child(1) { --meter-index: 1; }
.audio-meter i:nth-child(2) { --meter-index: 2; }
.audio-meter i:nth-child(3) { --meter-index: 3; }
.audio-meter i:nth-child(4) { --meter-index: 4; }
.audio-meter i:nth-child(5) { --meter-index: 5; }
.audio-meter i:nth-child(6) { --meter-index: 6; }
.audio-meter i:nth-child(7) { --meter-index: 7; }
.audio-meter i:nth-child(8) { --meter-index: 8; }
.audio-meter i:nth-child(9) { --meter-index: 9; }
.audio-meter i:nth-child(10) { --meter-index: 10; }
.audio-meter i:nth-child(11) { --meter-index: 11; }
.audio-meter i:nth-child(12) { --meter-index: 12; }
.audio-meter i:nth-child(13) { --meter-index: 13; }
.audio-meter i:nth-child(14) { --meter-index: 14; }
.audio-meter i:nth-child(15) { --meter-index: 15; }
.audio-meter i:nth-child(16) { --meter-index: 16; }
.audio-meter i:nth-child(17) { --meter-index: 17; }

body[data-state="thinking"] .audio-meter i {
  color: var(--active);
  opacity: 0.75;
  animation: thinking 700ms var(--ease) infinite alternate;
  animation-delay: calc(var(--meter-index, 0) * -35ms);
}

@keyframes meter {
  from { transform: scaleY(calc(var(--meter-height, 0.4) * 0.38)); }
  to { transform: scaleY(var(--meter-height, 0.4)); }
}

@keyframes thinking {
  from { transform: translateY(-0.25rem) scaleY(0.1); }
  to { transform: translateY(0.25rem) scaleY(0.35); }
}

.conversation h2 {
  margin: var(--space-xs) 0 0;
  font-size: 2.75rem;
  line-height: 1.08;
  letter-spacing: -0.04em;
  font-weight: 700;
  text-wrap: balance;
}

.state-detail {
  max-width: 34ch;
  margin: 0;
  color: var(--muted);
  font-size: 1rem;
  line-height: 1.6;
  text-wrap: pretty;
}

.current-transcript {
  min-height: 7rem;
  display: flex;
  align-items: center;
  padding: var(--space-lg) 0;
  border-top: 1px solid var(--line);
}

.current-transcript p {
  max-width: 38ch;
  margin: 0 auto;
  color: var(--ink);
  font-size: 1.125rem;
  line-height: 1.65;
  text-align: center;
  text-wrap: pretty;
}

.current-transcript p.is-placeholder { color: var(--muted); }

.call-controls {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr;
  align-items: end;
  gap: var(--space-md);
  padding-top: var(--space-lg);
}

.control-button {
  min-width: 0;
  min-height: 6rem;
  padding: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: var(--space-xs);
  color: var(--ink);
  background: transparent;
  border: 0;
  cursor: pointer;
}

.control-button:disabled {
  color: #73737d;
  cursor: not-allowed;
}

.control-icon {
  width: 4rem;
  height: 4rem;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--surface);
  transition:
    transform 120ms var(--ease),
    background-color 180ms var(--ease),
    color 180ms var(--ease);
}

.control-icon svg,
.icon-button svg {
  width: 1.65rem;
  height: 1.65rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.primary-control .control-icon {
  width: 5.25rem;
  height: 5.25rem;
  color: #04130e;
  background: var(--active);
}

.phone-end { display: none; }

body[data-active="true"] .primary-control .control-icon {
  color: white;
  background: var(--danger);
}

body[data-active="true"] .phone-start { display: none; }
body[data-active="true"] .phone-end { display: block; }

body[data-muted="true"] #mute-button .control-icon {
  color: #04130e;
  background: var(--active);
}

@media (hover: hover) {
  .control-button:not(:disabled):hover .control-icon { background: var(--surface-strong); }
  .primary-control:not(:disabled):hover .control-icon { filter: brightness(1.08); }
  body[data-active="true"] .primary-control:hover .control-icon { background: #dc2626; }
}

.control-button:not(:disabled):active .control-icon { transform: scale(0.94); }

dialog {
  width: min(calc(100% - 2rem), 36rem);
  max-height: min(80vh, 45rem);
  padding: 0;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 1rem;
}

dialog::backdrop { background: rgb(0 0 0 / 72%); }

.dialog-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-lg);
  border-bottom: 1px solid var(--line);
}

.dialog-header h2,
#access-dialog h2 {
  margin: 0;
  font-size: 1.25rem;
  line-height: 1.25;
}

.dialog-header p,
#access-dialog p {
  margin: 0.35rem 0 0;
  color: var(--muted);
}

.icon-button {
  width: 2.75rem;
  height: 2.75rem;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  padding: 0;
  color: var(--ink);
  background: transparent;
  border: 0;
  border-radius: 50%;
  cursor: pointer;
}

.transcript-list {
  max-height: 60vh;
  margin: 0;
  padding: var(--space-sm) var(--space-lg) var(--space-lg);
  list-style: none;
  overflow-y: auto;
}

.transcript-list li {
  padding: var(--space-md) 0;
  border-bottom: 1px solid var(--line);
}

.transcript-list li:last-child { border-bottom: 0; }

.transcript-list strong {
  color: var(--active);
  font-size: 0.875rem;
}

.transcript-list p {
  margin: 0.25rem 0 0;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.transcript-list .user-turn strong { color: var(--muted); }
.empty-transcript { color: var(--muted); }

#access-dialog form { padding: var(--space-lg); }

#access-dialog label {
  display: block;
  margin: var(--space-lg) 0 var(--space-xs);
  font-weight: 600;
}

#access-dialog input {
  width: 100%;
  min-height: 3rem;
  padding: var(--space-sm) var(--space-md);
  color: var(--ink);
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 0.625rem;
}

#access-dialog .form-error {
  min-height: 1.5rem;
  color: #fca5a5;
  font-size: 0.875rem;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-lg);
}

.text-button,
.submit-button {
  min-height: 2.75rem;
  padding: var(--space-sm) var(--space-md);
  border-radius: 0.625rem;
  cursor: pointer;
}

.text-button {
  color: var(--ink);
  background: transparent;
  border: 1px solid var(--line);
}

.submit-button {
  color: #04130e;
  background: var(--active);
  border: 1px solid var(--active);
  font-weight: 700;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

noscript {
  position: fixed;
  inset: auto 1rem 1rem;
  padding: 1rem;
  color: var(--ink);
  background: var(--danger);
}

@media (max-height: 43rem) and (orientation: landscape) {
  .voice-shell { width: min(100%, 58rem); }
  .conversation {
    min-height: 12rem;
    padding: var(--space-md) 0;
  }
  .audio-meter { height: 4rem; }
  .conversation h2 { font-size: 2rem; }
  .current-transcript {
    min-height: 4rem;
    padding: var(--space-sm) 0;
  }
  .call-controls { padding-top: var(--space-sm); }
  .control-icon { width: 3.25rem; height: 3.25rem; }
  .primary-control .control-icon { width: 4rem; height: 4rem; }
}

@media (min-width: 48rem) {
  .voice-shell { padding-top: max(2.5rem, env(safe-area-inset-top)); }
  .conversation h2 { font-size: 3rem; }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  body[data-state="listening"] .audio-meter i,
  body[data-state="speaking"] .audio-meter i {
    transform: scaleY(var(--meter-height, 0.4));
  }
}
"""


AUDIO_WORKLET_JS = r"""
class SecretaryCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Int16Array(640);
    this.offset = 0;
    this.phase = 0;
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;

    const ratio = sampleRate / 16000;
    let position = this.phase;
    let energy = 0;
    let count = 0;

    while (position < input.length) {
      const left = Math.floor(position);
      const right = Math.min(left + 1, input.length - 1);
      const blend = position - left;
      const sample = Math.max(-1, Math.min(1, input[left] * (1 - blend) + input[right] * blend));
      this.chunk[this.offset++] = sample < 0 ? sample * 32768 : sample * 32767;
      energy += sample * sample;
      count += 1;

      if (this.offset === this.chunk.length) {
        const data = this.chunk.buffer;
        this.port.postMessage({ type: "audio", data, level: Math.sqrt(energy / Math.max(1, count)) }, [data]);
        this.chunk = new Int16Array(640);
        this.offset = 0;
        energy = 0;
        count = 0;
      }
      position += ratio;
    }

    this.phase = position - input.length;
    return true;
  }
}

registerProcessor("secretary-capture", SecretaryCaptureProcessor);
"""


VOICE_JS = r"""
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    call: $("call-button"),
    callLabel: $("call-label"),
    mute: $("mute-button"),
    transcript: $("transcript-button"),
    transcriptDialog: $("transcript-dialog"),
    transcriptList: $("transcript-list"),
    closeTranscript: $("close-transcript"),
    state: $("voice-state"),
    detail: $("state-detail"),
    connection: $("connection-label"),
    latest: $("latest-transcript"),
    announcer: $("announcer"),
    accessDialog: $("access-dialog"),
    accessForm: $("access-form"),
    accessKey: $("access-key"),
    accessError: $("access-error"),
    cancelAccess: $("cancel-access"),
  };

  const app = {
    active: false,
    muted: false,
    ready: false,
    manualClose: false,
    reconnects: 0,
    generation: 0,
    socket: null,
    stream: null,
    audioContext: null,
    captureNode: null,
    silentGain: null,
    playbackSources: new Set(),
    playbackAt: 0,
    modelTurnActive: false,
    tokenConfig: null,
    resumeHandle: "",
    userText: "",
    assistantText: "",
    committedUserText: "",
    committedAssistantText: "",
    callId: "",
    transcript: [],
  };

  function setState(state, title, detail, connection) {
    document.body.dataset.state = state;
    $("voice-main").setAttribute("aria-busy", String(state === "connecting" || state === "thinking"));
    els.state.textContent = title;
    els.detail.textContent = detail;
    els.connection.textContent = connection;
    els.announcer.textContent = `${connection}. ${title}. ${detail}`;
  }

  function setActive(active) {
    app.active = active;
    document.body.dataset.active = String(active);
    els.callLabel.textContent = active ? "End" : "Start";
    els.call.setAttribute("aria-label", active ? "End voice session" : "Start voice session");
    els.mute.disabled = !active;
  }

  function setMuted(muted) {
    app.muted = muted;
    document.body.dataset.muted = String(muted);
    els.mute.querySelector("span:last-child").textContent = muted ? "Unmute" : "Mute";
    els.mute.setAttribute("aria-pressed", String(muted));
    if (muted) {
      setState("muted", "Muted", "Tap Unmute when you are ready.", "Connected");
    } else if (app.ready) {
      setState("listening", "Listening", "What would you like me to handle?", "Connected");
    }
  }

  function accessHeaders() {
    const key = sessionStorage.getItem("voiceAccessKey");
    return key ? { "X-Voice-App-Key": key } : {};
  }

  async function fetchJSON(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { ...accessHeaders(), ...(options.headers || {}) },
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      const error = new Error(payload.detail || "The server could not complete the request.");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function showAccessDialog(message = "") {
    els.accessError.textContent = message;
    if (!els.accessDialog.open) els.accessDialog.showModal();
    requestAnimationFrame(() => els.accessKey.focus());
  }

  async function getSessionToken() {
    return fetchJSON("/api/v1/voice/session-token", { method: "POST" });
  }

  function getMicrophone() {
    if (!window.isSecureContext && !["localhost", "127.0.0.1"].includes(location.hostname)) {
      throw new Error("Microphone access needs HTTPS. Open the secure app URL and try again.");
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser does not support microphone access.");
    }
    return navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
  }

  async function prepareAudio(stream) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext || !window.AudioWorkletNode) {
      throw new Error("This browser does not support low-latency audio.");
    }
    app.audioContext = new AudioContext({ latencyHint: "interactive" });
    await app.audioContext.audioWorklet.addModule("/voice/audio-worklet.js?v=3");
    await app.audioContext.resume();

    const source = app.audioContext.createMediaStreamSource(stream);
    app.captureNode = new AudioWorkletNode(app.audioContext, "secretary-capture");
    app.silentGain = app.audioContext.createGain();
    app.silentGain.gain.value = 0;
    source.connect(app.captureNode).connect(app.silentGain).connect(app.audioContext.destination);

    app.captureNode.port.onmessage = (event) => {
      if (
        event.data?.type !== "audio" ||
        !app.ready ||
        app.muted ||
        app.socket?.readyState !== WebSocket.OPEN ||
        app.socket.bufferedAmount > 65536
      ) return;

      app.socket.send(JSON.stringify({
        realtimeInput: {
          audio: {
            data: bytesToBase64(new Uint8Array(event.data.data)),
            mimeType: "audio/pcm;rate=16000",
          },
        },
      }));
    };
  }

  function bytesToBase64(bytes) {
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return btoa(binary);
  }

  function base64ToPCM(base64) {
    const raw = atob(base64);
    const pcm = new Float32Array(raw.length / 2);
    for (let index = 0; index < pcm.length; index += 1) {
      const low = raw.charCodeAt(index * 2);
      const high = raw.charCodeAt(index * 2 + 1);
      let value = (high << 8) | low;
      if (value >= 0x8000) value -= 0x10000;
      pcm[index] = value / 32768;
    }
    return pcm;
  }

  function playAudio(base64) {
    if (!app.audioContext) return;
    const pcm = base64ToPCM(base64);
    const buffer = app.audioContext.createBuffer(1, pcm.length, 24000);
    buffer.copyToChannel(pcm, 0);
    const source = app.audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(app.audioContext.destination);

    const startAt = Math.max(app.audioContext.currentTime + 0.025, app.playbackAt);
    app.playbackAt = startAt + buffer.duration;
    app.playbackSources.add(source);
    source.onended = () => {
      app.playbackSources.delete(source);
      if (!app.playbackSources.size && !app.modelTurnActive && app.active && !app.muted) {
        setState("listening", "Listening", "What would you like me to handle?", "Connected");
      }
    };
    source.start(startAt);
    setState("speaking", "Speaking", "You can interrupt at any time.", "Connected");
  }

  function stopPlayback() {
    for (const source of app.playbackSources) {
      try { source.stop(); } catch {}
    }
    app.playbackSources.clear();
    app.playbackAt = app.audioContext?.currentTime || 0;
  }

  function mergeText(current, incoming) {
    const text = String(incoming || "").trim();
    if (!text) return current;
    if (!current || text.startsWith(current)) return text;
    if (current.endsWith(text)) return current;
    return `${current} ${text}`.trim();
  }

  function showLatest(text, placeholder = false) {
    els.latest.textContent = text;
    els.latest.classList.toggle("is-placeholder", placeholder);
  }

  function appendTranscript(speaker, text) {
    const value = String(text || "").trim();
    if (!value) return;
    app.transcript.push({ speaker, text: value });
    if (app.transcript.length > 40) app.transcript.shift();
    renderTranscript();
  }

  function renderTranscript() {
    els.transcriptList.replaceChildren();
    if (!app.transcript.length) {
      const empty = document.createElement("li");
      empty.className = "empty-transcript";
      empty.textContent = "Start a conversation to see the transcript.";
      els.transcriptList.append(empty);
      return;
    }
    for (const turn of app.transcript) {
      const item = document.createElement("li");
      item.className = turn.speaker === "You" ? "user-turn" : "assistant-turn";
      const label = document.createElement("strong");
      label.textContent = turn.speaker;
      const text = document.createElement("p");
      text.textContent = turn.text;
      item.append(label, text);
      els.transcriptList.append(item);
    }
  }

  function commitTurn() {
    if (app.userText && app.userText !== app.committedUserText) {
      appendTranscript("You", app.userText);
      app.committedUserText = app.userText;
      showLatest(app.userText);
    }
    if (app.assistantText && app.assistantText !== app.committedAssistantText) {
      appendTranscript("Secretary", app.assistantText);
      app.committedAssistantText = app.assistantText;
    }
    app.userText = "";
    app.assistantText = "";
  }

  function setupMessage() {
    const config = app.tokenConfig;
    const language = config.language === "ru" ? "Russian" : "English";
    const setup = {
      model: `models/${config.model}`,
      generationConfig: {
        responseModalities: ["AUDIO"],
        speechConfig: {
          voiceConfig: { prebuiltVoiceConfig: { voiceName: config.voice } },
        },
      },
      inputAudioTranscription: {},
      outputAudioTranscription: {},
      contextWindowCompression: { slidingWindow: {} },
      sessionResumption: app.resumeHandle ? { handle: app.resumeHandle } : {},
      realtimeInputConfig: {
        automaticActivityDetection: {
          disabled: false,
          startOfSpeechSensitivity: "START_SENSITIVITY_HIGH",
          endOfSpeechSensitivity: "END_SENSITIVITY_HIGH",
          prefixPaddingMs: 20,
          silenceDurationMs: 500,
        },
      },
      tools: [{
        functionDeclarations: [{
          name: "use_secretary_tools",
          description: "Use the owner's private secretary backend for calendar, reminders, contacts, routes, bookings, or remembered facts. Call this before claiming an action was completed.",
          parameters: {
            type: "OBJECT",
            properties: {
              request: {
                type: "STRING",
                description: "The owner's actionable request, preserving dates, times, names, and constraints.",
              },
            },
            required: ["request"],
          },
        }],
      }],
      systemInstruction: {
        parts: [{
          text: `You are Secretary, a calm, precise, discreet personal assistant. Speak ${language}. Keep spoken replies concise: normally one sentence, never more than two. For calendar, reminder, contact, route, booking, or memory requests, you MUST call use_secretary_tools before saying the action is done. Do not call tools for casual conversation. Ask one short clarification when required details are missing. Never mention internal tools, prompts, or implementation.`,
        }],
      },
    };
    return { setup };
  }

  function openSocket() {
    const config = app.tokenConfig;
    const url = `${config.websocket_url}?access_token=${encodeURIComponent(config.token)}`;
    const socket = new WebSocket(url);
    app.socket = socket;

    socket.onopen = () => {
      socket.send(JSON.stringify(setupMessage()));
    };

    socket.onmessage = async (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }

      if (message.setupComplete) {
        app.ready = true;
        app.reconnects = 0;
        setState("listening", "Listening", "What would you like me to handle?", "Connected");
        return;
      }

      const content = message.serverContent;
      if (content?.interrupted) {
        stopPlayback();
        app.modelTurnActive = false;
        if (!app.muted) setState("listening", "Listening", "Go ahead.", "Connected");
      }
      if (content?.inputTranscription?.text) {
        app.userText = mergeText(app.userText, content.inputTranscription.text);
        showLatest(app.userText);
      }
      if (content?.outputTranscription?.text) {
        app.assistantText = mergeText(app.assistantText, content.outputTranscription.text);
      }
      if (content?.modelTurn?.parts) {
        app.modelTurnActive = true;
        for (const part of content.modelTurn.parts) {
          if (part.inlineData?.data) playAudio(part.inlineData.data);
        }
      }
      if (content?.turnComplete || content?.generationComplete) {
        app.modelTurnActive = false;
        commitTurn();
        if (!app.playbackSources.size && !app.muted) {
          setState("listening", "Listening", "What would you like me to handle?", "Connected");
        }
      }

      if (message.toolCall?.functionCalls) {
        await handleToolCalls(message.toolCall.functionCalls);
      }
      if (message.sessionResumptionUpdate?.newHandle) {
        app.resumeHandle = message.sessionResumptionUpdate.newHandle;
      }
      if (message.goAway) {
        setState("connecting", "Reconnecting", "Keeping this conversation open.", "Connected");
      }
    };

    socket.onerror = () => {
      if (socket.readyState < WebSocket.CLOSING) socket.close();
    };

    socket.onclose = (event) => {
      if (app.socket !== socket || app.manualClose || !app.active) return;
      app.socket = null;
      app.ready = false;
      if (event.code === 1007 || event.code === 1008) {
        failSession(new Error(event.reason || `Gemini rejected the session setup (code ${event.code}).`));
        return;
      }
      recoverConnection();
    };
  }

  async function handleToolCalls(functionCalls) {
    setState("thinking", "Working", "Handling that securely.", "Connected");
    const responses = await Promise.all(functionCalls.map(async (call) => {
      try {
        if (call.name !== "use_secretary_tools") {
          return { id: call.id, name: call.name, response: { error: "Unknown tool." } };
        }
        const request = String(call.args?.request || "").trim();
        if (!request) {
          return { id: call.id, name: call.name, response: { error: "The request was empty." } };
        }
        const result = await fetchJSON("/api/v1/voice/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ call_id: app.callId, request }),
        });
        return {
          id: call.id,
          name: call.name,
          response: {
            result: result.reply,
            intent: result.intent,
            actions: result.action_items,
          },
        };
      } catch (error) {
        return {
          id: call.id,
          name: call.name,
          response: { error: error.message || "The secretary action failed." },
        };
      }
    }));

    if (app.socket?.readyState === WebSocket.OPEN) {
      app.socket.send(JSON.stringify({ toolResponse: { functionResponses: responses } }));
    }
  }

  async function recoverConnection() {
    if (!app.active || app.manualClose) return;
    if (app.reconnects >= 3) {
      failSession(new Error("The live connection ended. Tap Retry to start a new session."));
      return;
    }
    app.reconnects += 1;
    setState("connecting", "Reconnecting", "Restoring the live connection.", "Connection lost");
    await new Promise((resolve) => setTimeout(resolve, 250 * app.reconnects));
    try {
      if (!app.resumeHandle) app.tokenConfig = await getSessionToken();
      openSocket();
    } catch (error) {
      recoverConnection();
    }
  }

  async function startSession() {
    if (app.active) {
      endSession();
      return;
    }

    setActive(true);
    app.manualClose = false;
    app.ready = false;
    app.reconnects = 0;
    app.resumeHandle = "";
    app.callId = `voice-${crypto.randomUUID?.() || Date.now()}`;
    const generation = ++app.generation;
    app.transcript = [];
    renderTranscript();
    showLatest("Your latest words will appear here.", true);
    setState("connecting", "Connecting", "Preparing a secure live session.", "Connecting");

    let stream;
    try {
      const [tokenConfig, microphone] = await Promise.all([getSessionToken(), getMicrophone()]);
      if (!app.active || generation !== app.generation) {
        microphone.getTracks().forEach((track) => track.stop());
        return;
      }
      app.tokenConfig = tokenConfig;
      stream = microphone;
      app.stream = microphone;
      await prepareAudio(microphone);
      openSocket();
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      if (error.status === 401) {
        endSession(false);
        showAccessDialog(error.message);
      } else {
        failSession(error);
      }
    }
  }

  function failSession(error) {
    const message = error?.name === "NotAllowedError"
      ? "Microphone access was blocked. Allow it in browser settings, then tap Retry."
      : error?.message || "The voice session could not start. Tap Retry.";
    cleanResources();
    setActive(false);
    els.callLabel.textContent = "Retry";
    showLatest(message);
    setState("error", "Couldn’t connect", message, "Unavailable");
  }

  function cleanResources() {
    app.generation += 1;
    app.ready = false;
    app.manualClose = true;
    stopPlayback();
    if (app.socket && app.socket.readyState < WebSocket.CLOSING) app.socket.close(1000, "User ended session");
    app.socket = null;
    app.stream?.getTracks().forEach((track) => track.stop());
    app.stream = null;
    app.captureNode?.disconnect();
    app.silentGain?.disconnect();
    app.captureNode = null;
    app.silentGain = null;
    if (app.audioContext && app.audioContext.state !== "closed") app.audioContext.close();
    app.audioContext = null;
    app.resumeHandle = "";
  }

  function endSession(resetView = true) {
    commitTurn();
    cleanResources();
    setActive(false);
    setMuted(false);
    if (resetView) {
      setState("idle", "Ready", "Tap Start to begin.", "Ready");
      showLatest("Your latest words will appear here.", true);
    }
  }

  els.call.addEventListener("click", startSession);
  els.mute.addEventListener("click", () => setMuted(!app.muted));
  els.transcript.addEventListener("click", () => els.transcriptDialog.showModal());
  els.closeTranscript.addEventListener("click", () => els.transcriptDialog.close());
  els.transcriptDialog.addEventListener("click", (event) => {
    if (event.target === els.transcriptDialog) els.transcriptDialog.close();
  });
  els.cancelAccess.addEventListener("click", () => els.accessDialog.close());
  els.accessForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const key = els.accessKey.value.trim();
    if (!key) {
      els.accessError.textContent = "Enter the access key.";
      els.accessKey.setAttribute("aria-invalid", "true");
      return;
    }
    els.accessKey.removeAttribute("aria-invalid");
    sessionStorage.setItem("voiceAccessKey", key);
    els.accessDialog.close();
    els.accessKey.value = "";
    startSession();
  });
  els.accessKey.addEventListener("input", () => {
    els.accessKey.removeAttribute("aria-invalid");
    els.accessError.textContent = "";
  });

  window.addEventListener("offline", () => {
    if (app.active) setState("connecting", "Offline", "Waiting for your connection.", "Connection lost");
  });
  window.addEventListener("online", () => {
    if (app.active && app.socket?.readyState !== WebSocket.OPEN) recoverConnection();
  });
  window.addEventListener("pagehide", cleanResources);

  document.body.dataset.state = "idle";
  document.body.dataset.active = "false";
  document.body.dataset.muted = "false";
  showLatest("Your latest words will appear here.", true);
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/voice/sw.js").catch(() => {}));
  }
})();
"""


SERVICE_WORKER_JS = r"""
const CACHE = "secretary-voice-v3";
const APP_SHELL = [
  "/voice/",
  "/voice/app.css?v=3",
  "/voice/app.js?v=3",
  "/voice/audio-worklet.js?v=3",
  "/voice/manifest.webmanifest?v=3",
  "/voice/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put("/voice/", copy));
          return response;
        })
        .catch(() => caches.match("/voice/"))
    );
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
"""


VOICE_MANIFEST = {
    "name": "Secretary",
    "short_name": "Secretary",
    "description": "Low-latency voice access to Secretary AI.",
    "start_url": "/voice/",
    "scope": "/voice/",
    "display": "standalone",
    "background_color": "#09090b",
    "theme_color": "#09090b",
    "orientation": "any",
    "icons": [
        {
            "src": "/voice/icon.svg",
            "sizes": "any",
            "type": "image/svg+xml",
            "purpose": "any maskable",
        }
    ],
}


VOICE_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="112" fill="#09090b"/>
  <g fill="#10b981">
    <rect x="92" y="228" width="24" height="56" rx="12"/>
    <rect x="136" y="198" width="24" height="116" rx="12"/>
    <rect x="180" y="156" width="24" height="200" rx="12"/>
    <rect x="224" y="108" width="24" height="296" rx="12"/>
    <rect x="268" y="142" width="24" height="228" rx="12"/>
    <rect x="312" y="184" width="24" height="144" rx="12"/>
    <rect x="356" y="218" width="24" height="76" rx="12"/>
    <rect x="400" y="236" width="20" height="40" rx="10"/>
  </g>
</svg>"""
