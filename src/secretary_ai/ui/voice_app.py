import asyncio
import base64
import json
import logging
import re
import secrets
import time
import warnings
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from google import genai
from pydantic import BaseModel, ConfigDict, Field, field_validator
from websockets.asyncio.client import ClientConnection, connect as websocket_connect

from secretary_ai.services.secretary import SecretaryService

router = APIRouter(include_in_schema=False)
logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver"}
_VOICE_RELAY_TICKET_TTL_SECONDS = 55
_VOICE_ASSET_VERSION = "11"
_GEMINI_LIVE_WS_HOST = "generativelanguage.googleapis.com"
_NO_STORE = {"Cache-Control": "no-store"}
_STATIC_HEADERS = {"Cache-Control": "public, max-age=3600"}
_PAGE_HEADERS = {
    **_NO_STORE,
    "Content-Security-Policy": (
        "default-src 'self'; "
        "connect-src 'self' ws://127.0.0.1:* ws://localhost:* "
        f"wss://{_GEMINI_LIVE_WS_HOST}; "
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
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    tool: str = Field(
        default="use_secretary_tools",
        min_length=2,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    arguments: dict[str, str] = Field(default_factory=dict, max_length=12)
    request: str = Field(default="", max_length=2000)

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, arguments: dict[str, str]) -> dict[str, str]:
        for key, value in arguments.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
                raise ValueError("Invalid tool argument name.")
            if len(value) > 1000:
                raise ValueError("Tool argument is too long.")
        return arguments


class VoiceMetricsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    session_ms: int = Field(ge=0, le=14_400_000)
    response_count: int = Field(ge=0, le=1000)
    response_latency_ms_total: int = Field(ge=0, le=14_400_000)
    response_latency_ms_max: int = Field(ge=0, le=600_000)
    barge_in_attempt_count: int = Field(ge=0, le=1000)
    interruption_count: int = Field(ge=0, le=1000)
    interruption_latency_ms_total: int = Field(ge=0, le=600_000)
    tool_call_count: int = Field(ge=0, le=1000)
    tool_latency_ms_total: int = Field(ge=0, le=14_400_000)
    tool_latency_ms_max: int = Field(ge=0, le=600_000)
    dropped_audio_chunks: int = Field(ge=0, le=1_000_000)
    reconnect_count: int = Field(ge=0, le=1000)


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
    request: Request,
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
                        "lock_additional_fields": [],
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

    tickets: dict[str, tuple[str, float]] = getattr(
        request.app.state,
        "voice_relay_tickets",
        {},
    )
    now_monotonic = time.monotonic()
    request.app.state.voice_relay_tickets = {
        ticket: value
        for ticket, value in tickets.items()
        if value[1] > now_monotonic
    }
    relay_ticket = secrets.token_urlsafe(24)
    request.app.state.voice_relay_tickets[relay_ticket] = (
        token,
        now_monotonic + _VOICE_RELAY_TICKET_TTL_SECONDS,
    )
    websocket_scheme = "wss" if request.url.scheme == "https" else "ws"
    websocket_url = f"{websocket_scheme}://{request.url.netloc}/api/v1/voice/live"
    api_version = settings.gemini_live_api_version
    direct_websocket_url = (
        f"wss://{_GEMINI_LIVE_WS_HOST}/ws/"
        f"google.ai.generativelanguage.{api_version}."
        "GenerativeService.BidiGenerateContentConstrained"
    )
    try:
        local_now = datetime.now(ZoneInfo(settings.timezone))
    except ZoneInfoNotFoundError:
        local_now = datetime.now(timezone.utc)
    return JSONResponse(
        {
            "token": relay_ticket,
            "live_token": token,
            "model": settings.gemini_live_model,
            "voice": settings.gemini_live_voice,
            "language": settings.language,
            "timezone": settings.timezone,
            "local_time": local_now.isoformat(timespec="minutes"),
            "websocket_url": websocket_url,
            "direct_websocket_url": direct_websocket_url,
        },
        headers=_NO_STORE,
    )


def _same_origin_websocket(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc.casefold() == (
        websocket.headers.get("host") or ""
    ).casefold()


def _record_relay_input_stats(text: str, stats: dict[str, int | float], call_id: str) -> None:
    try:
        payload = json.loads(text)
        audio_data = (
            ((payload.get("realtimeInput") or {}).get("audio") or {}).get("data")
            if isinstance(payload, dict)
            else None
        )
    except (TypeError, ValueError):
        return
    if not isinstance(audio_data, str):
        return
    try:
        raw_audio = base64.b64decode(audio_data)
        samples = memoryview(raw_audio).cast("h")
        peak = max((abs(sample) for sample in samples), default=0)
        stats["input_chunks"] += 1
        stats["input_bytes"] += len(raw_audio)
        stats["input_peak"] = max(stats["input_peak"], peak)
        chunks = int(stats["input_chunks"])
        if chunks in {1, 25} or chunks % 250 == 0:
            logger.info(
                "Voice relay input call=%s chunks=%d bytes=%d peak=%d",
                call_id,
                chunks,
                int(stats["input_bytes"]),
                int(stats["input_peak"]),
            )
    except (TypeError, ValueError):
        stats["invalid_audio_chunks"] += 1


def _record_relay_output_stats(text: str, stats: dict[str, int | float], call_id: str) -> None:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return
    if payload.get("setupComplete") is not None and not stats["setup_complete"]:
        stats["setup_complete"] = 1
        logger.info("Voice relay ready call=%s", call_id)
    content = payload.get("serverContent") or {}
    transcription = (content.get("inputTranscription") or {}).get("text", "")
    if transcription:
        was_empty = not stats["transcription_chars"]
        stats["transcription_chars"] += len(transcription)
        if was_empty:
            logger.info("Voice relay recognized speech call=%s", call_id)
    output_chunks = 0
    for part in (content.get("modelTurn") or {}).get("parts", []):
        audio = (part.get("inlineData") or {}).get("data", "")
        if audio:
            output_chunks += 1
            stats["output_audio_chars"] += len(audio)
    if output_chunks:
        was_empty = not stats["output_chunks"]
        stats["output_chunks"] += output_chunks
        if was_empty:
            logger.info("Voice relay response audio call=%s", call_id)
    if content.get("turnComplete") or content.get("generationComplete"):
        stats["completed_turns"] += 1


async def _relay_browser_messages(
    websocket: WebSocket,
    upstream: ClientConnection,
    stats: dict[str, int | float],
    call_id: str,
) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("text") is not None:
            text = message["text"]
            await upstream.send(text)
            _record_relay_input_stats(text, stats, call_id)
        elif message.get("bytes") is not None:
            await upstream.send(message["bytes"])


async def _relay_gemini_messages(
    websocket: WebSocket,
    upstream: ClientConnection,
    stats: dict[str, int | float],
    call_id: str,
) -> None:
    async for message in upstream:
        text = message if isinstance(message, str) else message.decode("utf-8")
        await websocket.send_text(text)
        _record_relay_output_stats(text, stats, call_id)


@router.websocket("/api/v1/voice/live")
async def voice_live_proxy(websocket: WebSocket) -> None:
    if not _same_origin_websocket(websocket):
        await websocket.close(code=1008, reason="The voice connection must come from this app.")
        return

    ticket = websocket.query_params.get("access_token", "")
    tickets: dict[str, tuple[str, float]] = getattr(
        websocket.app.state,
        "voice_relay_tickets",
        {},
    )
    ticket_data = tickets.pop(ticket, None)
    if not ticket_data or ticket_data[1] <= time.monotonic():
        await websocket.close(code=1008, reason="The voice session expired. Tap Retry.")
        return

    settings = websocket.app.state.secretary.settings
    call_id = re.sub(
        r"[^A-Za-z0-9_.:-]+",
        "",
        websocket.query_params.get("call_id", ""),
    )[:80] or "unknown"
    stats: dict[str, int | float] = {
        "started_at": time.monotonic(),
        "setup_complete": 0,
        "input_chunks": 0,
        "input_bytes": 0,
        "input_peak": 0,
        "invalid_audio_chunks": 0,
        "transcription_chars": 0,
        "output_chunks": 0,
        "output_audio_chars": 0,
        "completed_turns": 0,
    }
    api_version = settings.gemini_live_api_version
    upstream_url = (
        "wss://generativelanguage.googleapis.com/ws/"
        f"google.ai.generativelanguage.{api_version}."
        "GenerativeService.BidiGenerateContentConstrained"
        f"?access_token={quote(ticket_data[0], safe='')}"
    )

    await websocket.accept()
    browser_task: asyncio.Task[None] | None = None
    gemini_task: asyncio.Task[None] | None = None
    try:
        async with websocket_connect(
            upstream_url,
            open_timeout=12,
            close_timeout=5,
            max_size=None,
            compression=None,
        ) as upstream:
            browser_task = asyncio.create_task(
                _relay_browser_messages(websocket, upstream, stats, call_id)
            )
            gemini_task = asyncio.create_task(
                _relay_gemini_messages(websocket, upstream, stats, call_id)
            )
            done, pending = await asyncio.wait(
                {browser_task, gemini_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()

            if gemini_task in done and browser_task not in done:
                code = upstream.close_code or 1011
                reason = (upstream.close_reason or "The Gemini voice connection ended.")[:120]
                await websocket.close(code=code, reason=reason)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Voice relay connection failed: %s", type(exc).__name__)
        try:
            await websocket.close(code=1011, reason="The Gemini voice connection failed. Tap Retry.")
        except RuntimeError:
            pass
    finally:
        for task in (browser_task, gemini_task):
            if task and not task.done():
                task.cancel()
        logger.info(
            "Voice relay closed call=%s duration_ms=%d setup=%d input_chunks=%d "
            "input_bytes=%d input_peak=%d invalid_chunks=%d transcription_chars=%d "
            "output_chunks=%d output_chars=%d completed_turns=%d",
            call_id,
            round((time.monotonic() - float(stats["started_at"])) * 1000),
            int(stats["setup_complete"]),
            int(stats["input_chunks"]),
            int(stats["input_bytes"]),
            int(stats["input_peak"]),
            int(stats["invalid_audio_chunks"]),
            int(stats["transcription_chars"]),
            int(stats["output_chunks"]),
            int(stats["output_audio_chars"]),
            int(stats["completed_turns"]),
        )


async def _run_voice_tool(
    secretary: SecretaryService,
    payload: VoiceActionRequest,
) -> dict:
    tool = payload.tool
    arguments = {key: value.strip() for key, value in payload.arguments.items()}

    if tool == "manage_calendar":
        request = arguments.get("request", "")
        if not request:
            raise HTTPException(status_code=422, detail="Calendar request is required.")
        operation = arguments.get("operation", "").strip().lower()
        if operation and operation not in {"read", "create", "cancel", "reminder"}:
            raise HTTPException(status_code=422, detail="Calendar operation is invalid.")
        result = await secretary.calendar.quick_reply_or_enqueue(
            call_id=payload.call_id,
            transcript=request,
            context={"source": "voice_app_tool", "calendar_operation": operation},
        )
        processed = None
        if result.get("queued"):
            processed = await secretary._process_queued_calendar_task(  # noqa: SLF001
                payload.call_id,
                str(result.get("task_id") or ""),
            )
        return {
            "tool": tool,
            "status": str((processed or {}).get("status") or result.get("status") or "unknown"),
            "reply": str((processed or {}).get("reply") or result.get("reply") or ""),
            "data": result,
        }

    if tool == "plan_route":
        result = await secretary.maps.plan_route(
            origin=arguments.get("origin", ""),
            destination=arguments.get("destination", ""),
            mode=arguments.get("mode", "driving"),
        )
        return {
            "tool": tool,
            "status": str(result.get("status") or "unknown"),
            "reply": str(result.get("details") or result.get("detail") or ""),
            "data": result,
        }

    if tool == "remember_fact":
        fact = arguments.get("fact", "")
        if not fact:
            raise HTTPException(status_code=422, detail="Fact is required.")
        record = secretary.memory.add_user_fact_if_requested(
            payload.call_id,
            f"remember that {fact}",
        )
        return {
            "tool": tool,
            "status": "saved" if record else "error",
            "reply": f"Remembered: {fact}" if record else "The fact could not be saved.",
            "data": {"fact": fact},
        }

    if tool == "recall_memory":
        query = arguments.get("query", "")
        if not query:
            raise HTTPException(status_code=422, detail="Memory query is required.")
        facts = secretary.memory.retrieve_user_fact(query, limit=3)
        return {
            "tool": tool,
            "status": "found" if facts else "not_found",
            "reply": "" if facts else "No matching memory was found.",
            "data": {"facts": [str(item.get("fact") or "") for item in facts]},
        }

    if tool == "search_booking":
        category = arguments.get("category", "")
        actions = {
            "restaurant": "find_restaurant",
            "hotel": "find_hotel",
            "event": "find_event",
            "travel": "find_travel",
            "evening": "plan_evening",
        }
        action = actions.get(category)
        if action is None:
            raise HTTPException(status_code=422, detail="Booking category is invalid.")
        result = await secretary.booking.search_by_action(
            action=action,
            payload=arguments.get("details", ""),
            extracted=arguments,
        )
        valid_results = [
            item
            for item in result.get("results") or []
            if item.get("title") and not item.get("error")
        ]
        return {
            "tool": tool,
            "status": "found" if valid_results else "not_found",
            "reply": str(result.get("voice_summary") or ""),
            "data": {
                "category": result.get("category"),
                "location": result.get("location"),
                "result_count": len(valid_results),
            },
        }

    if tool != "use_secretary_tools":
        raise HTTPException(status_code=400, detail="Unknown voice tool.")
    request = payload.request.strip() or arguments.get("request", "")
    if not request:
        raise HTTPException(status_code=422, detail="Tool request is required.")
    result = await secretary.live_agent_respond(
        call_id=payload.call_id,
        transcript=request,
        context={"source": "voice_app"},
        speak_response=False,
    )
    return {
        "tool": tool,
        "status": "ok",
        "reply": result.reply,
        "intent": result.intent.value,
        "action_items": result.action_items,
        "requires_human": result.requires_human,
    }


@router.post("/api/v1/voice/action")
async def voice_action(
    payload: VoiceActionRequest,
    secretary: SecretaryService = Depends(_require_access),
) -> JSONResponse:
    return JSONResponse(await _run_voice_tool(secretary, payload), headers=_NO_STORE)


@router.post("/api/v1/voice/metrics", status_code=status.HTTP_204_NO_CONTENT)
async def voice_metrics(
    payload: VoiceMetricsRequest,
    _: SecretaryService = Depends(_require_access),
) -> Response:
    logger.info(
        "Voice session metrics call=%s duration_ms=%d responses=%d response_avg_ms=%d "
        "response_max_ms=%d barge_attempts=%d interruptions=%d interruption_avg_ms=%d tools=%d "
        "tool_avg_ms=%d tool_max_ms=%d dropped_chunks=%d reconnects=%d",
        payload.call_id,
        payload.session_ms,
        payload.response_count,
        round(payload.response_latency_ms_total / max(1, payload.response_count)),
        payload.response_latency_ms_max,
        payload.barge_in_attempt_count,
        payload.interruption_count,
        round(payload.interruption_latency_ms_total / max(1, payload.interruption_count)),
        payload.tool_call_count,
        round(payload.tool_latency_ms_total / max(1, payload.tool_call_count)),
        payload.tool_latency_ms_max,
        payload.dropped_audio_chunks,
        payload.reconnect_count,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


VOICE_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#09090b">
    <meta name="description" content="Low-latency voice access to Secretary AI.">
    <title>Secretary</title>
    <link rel="manifest" href="/voice/manifest.webmanifest?v=11">
    <link rel="icon" href="/voice/icon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="/voice/app.css?v=11">
    <script src="/voice/app.js?v=11" defer></script>
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
        <button class="icon-button header-settings" id="settings-button" type="button" aria-label="Open settings" aria-haspopup="dialog" aria-controls="settings-dialog">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>
        </button>
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

    <dialog id="settings-dialog" aria-labelledby="settings-title" aria-describedby="settings-description">
      <div class="dialog-header">
        <div>
          <h2 id="settings-title">Settings</h2>
          <p id="settings-description">Language and microphone changes apply to your next conversation.</p>
        </div>
        <button class="icon-button" id="close-settings" type="button" aria-label="Close settings">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>
        </button>
      </div>

      <div class="settings-body">
        <section class="settings-section" aria-labelledby="language-heading">
          <h3 id="language-heading">Language</h3>
          <label for="language-select">Conversation language</label>
          <select id="language-select" aria-describedby="language-help">
            <option value="en">English</option>
            <option value="ru">Russian</option>
          </select>
          <p class="field-help" id="language-help">Secretary will listen and reply in this language.</p>
        </section>

        <section class="settings-section" aria-labelledby="connectors-heading">
          <div class="section-heading">
            <h3 id="connectors-heading">Connectors</h3>
            <button class="small-button" id="refresh-connectors" type="button">Refresh</button>
          </div>
          <ul class="connector-list" id="connector-list" aria-live="polite" aria-busy="true">
            <li class="connector-placeholder">Checking connector status…</li>
          </ul>
          <a class="manage-link" href="/dashboard">Manage connectors <span aria-hidden="true">→</span></a>
        </section>

        <section class="settings-section" aria-labelledby="microphone-heading">
          <h3 id="microphone-heading">Microphone</h3>
          <label for="microphone-select">Input device</label>
          <select id="microphone-select" aria-describedby="microphone-help microphone-status">
            <option value="">System default</option>
          </select>
          <p class="field-help" id="microphone-help">The automatic choice avoids known virtual microphones.</p>
          <div class="microphone-test">
            <button class="text-button" id="test-microphone" type="button">Test microphone</button>
            <meter id="microphone-level" min="0" max="1" low="0.02" high="0.12" optimum="0.25" value="0" aria-label="Microphone input level"></meter>
          </div>
          <p class="field-status" id="microphone-status" role="status">Choose Test microphone to check the input.</p>
        </section>
      </div>

      <div class="settings-footer">
        <button class="submit-button" id="done-settings" type="button">Done</button>
      </div>
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
input,
select {
  font: inherit;
}

button {
  color: inherit;
  -webkit-tap-highlight-color: transparent;
}

button:focus-visible,
input:focus-visible,
select:focus-visible,
a:focus-visible {
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
  position: relative;
  width: 100%;
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

.header-settings {
  position: absolute;
  top: -0.35rem;
  right: 0;
  color: var(--muted);
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

.icon-button:hover { background: var(--surface-strong); }

.settings-body {
  max-height: min(60vh, 36rem);
  padding: 0 var(--space-lg);
  overflow-y: auto;
}

.settings-section {
  padding: var(--space-lg) 0;
  border-bottom: 1px solid var(--line);
}

.settings-section:last-child { border-bottom: 0; }

.settings-section h3 {
  margin: 0 0 var(--space-md);
  font-size: 1rem;
  line-height: 1.3;
}

.settings-section label {
  display: block;
  margin-bottom: var(--space-xs);
  font-weight: 600;
}

.settings-section select {
  width: 100%;
  min-height: 3rem;
  padding: var(--space-sm) 2.5rem var(--space-sm) var(--space-md);
  color: var(--ink);
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 0.625rem;
}

.field-help,
.field-status {
  margin: var(--space-xs) 0 0;
  color: var(--muted);
  font-size: 0.875rem;
}

.field-status[data-result="success"] { color: #86efac; }
.field-status[data-result="error"] { color: #fca5a5; }

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
}

.section-heading h3 { margin: 0; }

.small-button {
  padding: 0.35rem 0.6rem;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-radius: 0.375rem;
  cursor: pointer;
}

.small-button:hover { color: var(--ink); background: var(--surface-strong); }
.small-button:disabled { cursor: wait; opacity: 0.65; }

.connector-list {
  margin: var(--space-sm) 0;
  padding: 0;
  list-style: none;
}

.connector-list li {
  min-height: 2.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  border-bottom: 1px solid var(--line);
}

.connector-list li:last-child { border-bottom: 0; }

.connector-name { font-weight: 600; }
.connector-placeholder { color: var(--muted); }

.readiness {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--muted);
  font-size: 0.875rem;
  white-space: nowrap;
}

.readiness::before {
  width: 0.5rem;
  height: 0.5rem;
  flex: 0 0 auto;
  content: "";
  background: var(--muted);
  border-radius: 50%;
}

.readiness[data-ready="true"] { color: #86efac; }
.readiness[data-ready="true"]::before { background: var(--active); }

.manage-link {
  display: inline-block;
  color: var(--ink);
  text-underline-offset: 0.2em;
}

.microphone-test {
  display: grid;
  grid-template-columns: auto minmax(5rem, 1fr);
  align-items: center;
  gap: var(--space-md);
  margin-top: var(--space-md);
}

.microphone-test meter {
  width: 100%;
  height: 0.75rem;
  accent-color: var(--active);
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--line);
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
const CAPTURE_SAMPLES = 320;

class SecretaryCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Int16Array(CAPTURE_SAMPLES);
    this.offset = 0;
    this.phase = 0;
  }

  process(inputs, outputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    const output = outputs[0]?.[0];
    if (output) output.set(input);

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
        this.chunk = new Int16Array(CAPTURE_SAMPLES);
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

class SecretaryPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.offset = 0;
    this.srcRate = 24000;
    this.playing = false;
    this.port.onmessage = (event) => {
      if (event.data?.type === "stop") {
        this.queue = [];
        this.offset = 0;
        this._setPlaying(false);
        return;
      }
      if (event.data?.type === "audio" && event.data.data) {
        this.queue.push(new Int16Array(event.data.data));
        this._setPlaying(true);
      }
    };
  }

  _setPlaying(playing) {
    if (this.playing === playing) return;
    this.playing = playing;
    this.port.postMessage({ type: "state", playing });
  }

  process(inputs, outputs) {
    const output = outputs[0]?.[0];
    if (!output) return true;
    if (!this.queue.length) {
      output.fill(0);
      this._setPlaying(false);
      return true;
    }

    const step = this.srcRate / sampleRate;
    for (let index = 0; index < output.length; index += 1) {
      while (this.queue.length && this.offset >= this.queue[0].length) {
        this.offset -= this.queue[0].length;
        this.queue.shift();
      }
      if (!this.queue.length) {
        output[index] = 0;
        continue;
      }
      const current = this.queue[0];
      const idx = Math.floor(this.offset);
      const frac = this.offset - idx;
      const s0 = current[idx] || 0;
      let s1 = s0;
      if (idx + 1 < current.length) s1 = current[idx + 1];
      else if (this.queue[1] && this.queue[1].length) s1 = this.queue[1][0];
      output[index] = (s0 + (s1 - s0) * frac) / 32768;
      this.offset += step;
    }
    if (!this.queue.length || (this.queue.length === 1 && this.offset >= this.queue[0].length)) {
      this.queue = [];
      this.offset = 0;
      this._setPlaying(false);
    }
    return true;
  }
}

registerProcessor("secretary-capture", SecretaryCaptureProcessor);
registerProcessor("secretary-playback", SecretaryPlaybackProcessor);
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
    settings: $("settings-button"),
    settingsDialog: $("settings-dialog"),
    closeSettings: $("close-settings"),
    doneSettings: $("done-settings"),
    language: $("language-select"),
    connectors: $("connector-list"),
    refreshConnectors: $("refresh-connectors"),
    microphone: $("microphone-select"),
    microphoneTest: $("test-microphone"),
    microphoneLevel: $("microphone-level"),
    microphoneStatus: $("microphone-status"),
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
    playbackNode: null,
    micSource: null,
    silentGain: null,
    playbackActive: false,
    pendingAudio: [],
    usingRelay: false,
    modelTurnActive: false,
    tokenConfig: null,
    warmToken: null,
    warmTokenAt: 0,
    prefetchInFlight: null,
    resumeHandle: "",
    userText: "",
    assistantText: "",
    committedUserText: "",
    committedAssistantText: "",
    callId: "",
    transcript: [],
    localSpeechFrames: 0,
    localBargeIn: false,
    localBargeInAt: 0,
    bargeInTimer: null,
    awaitingFirstAudio: false,
    lastUserActivityAt: 0,
    metricsSent: false,
    metrics: null,
    cancelledToolCalls: new Set(),
    toolControllers: new Map(),
    toolResults: new Map(),
    microphoneLabel: "",
    capturePeak: 0,
    silenceTimer: null,
    microphoneTestStream: null,
    microphoneTestContext: null,
    microphoneTestFrame: 0,
    microphoneTestTimer: null,
    microphoneTestPeak: 0,
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
    if (muted && !app.muted) endAudioStream();
    app.muted = muted;
    app.localSpeechFrames = 0;
    document.body.dataset.muted = String(muted);
    els.mute.querySelector("span:last-child").textContent = muted ? "Unmute" : "Mute";
    els.mute.setAttribute("aria-pressed", String(muted));
    if (muted) {
      app.pendingAudio = [];
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
    const config = await fetchJSON("/api/v1/voice/session-token", { method: "POST" });
    const language = localStorage.getItem("voiceLanguage");
    if (["en", "ru"].includes(language)) config.language = language;
    return config;
  }

  function takeWarmToken() {
    if (app.warmToken && performance.now() - app.warmTokenAt < 45000) {
      const config = app.warmToken;
      app.warmToken = null;
      app.warmTokenAt = 0;
      return config;
    }
    return null;
  }

  function prefetchToken() {
    if (app.active || app.prefetchInFlight) return;
    if (app.warmToken && performance.now() - app.warmTokenAt < 45000) return;
    app.prefetchInFlight = getSessionToken()
      .then((config) => {
        app.warmToken = config;
        app.warmTokenAt = performance.now();
      })
      .catch(() => {})
      .finally(() => {
        app.prefetchInFlight = null;
      });
  }

  function endAudioStream() {
    if (app.ready && app.socket?.readyState === WebSocket.OPEN) {
      app.socket.send(JSON.stringify({ realtimeInput: { audioStreamEnd: true } }));
    }
  }

  function newMetrics() {
    return {
      startedAt: performance.now(),
      responseCount: 0,
      responseLatencyTotal: 0,
      responseLatencyMax: 0,
      bargeInAttemptCount: 0,
      interruptionCount: 0,
      interruptionLatencyTotal: 0,
      toolCallCount: 0,
      toolLatencyTotal: 0,
      toolLatencyMax: 0,
      droppedAudioChunks: 0,
      reconnectCount: 0,
    };
  }

  function recordFirstAudio() {
    if (!app.awaitingFirstAudio || !app.lastUserActivityAt || !app.metrics) return;
    const latency = Math.max(0, Math.round(performance.now() - app.lastUserActivityAt));
    app.metrics.responseCount += 1;
    app.metrics.responseLatencyTotal += latency;
    app.metrics.responseLatencyMax = Math.max(app.metrics.responseLatencyMax, latency);
    app.awaitingFirstAudio = false;
    app.lastUserActivityAt = 0;
  }

  function sendMetrics() {
    if (app.metricsSent || !app.metrics || !app.callId) return;
    app.metricsSent = true;
    const metrics = app.metrics;
    const payload = {
      call_id: app.callId,
      session_ms: Math.max(0, Math.round(performance.now() - metrics.startedAt)),
      response_count: metrics.responseCount,
      response_latency_ms_total: metrics.responseLatencyTotal,
      response_latency_ms_max: metrics.responseLatencyMax,
      barge_in_attempt_count: metrics.bargeInAttemptCount,
      interruption_count: metrics.interruptionCount,
      interruption_latency_ms_total: metrics.interruptionLatencyTotal,
      tool_call_count: metrics.toolCallCount,
      tool_latency_ms_total: metrics.toolLatencyTotal,
      tool_latency_ms_max: metrics.toolLatencyMax,
      dropped_audio_chunks: metrics.droppedAudioChunks,
      reconnect_count: metrics.reconnectCount,
    };
    fetch("/api/v1/voice/metrics", {
      method: "POST",
      headers: { ...accessHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {});
  }

  function microphoneConstraints(deviceId = "") {
    return {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      latency: 0,
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    };
  }

  function isVirtualMicrophone(label) {
    return /nvidia broadcast|virtual|screaming bee|line \d|cable/i.test(label);
  }

  async function getMicrophone() {
    if (!window.isSecureContext && !["localhost", "127.0.0.1"].includes(location.hostname)) {
      throw new Error("Microphone access needs HTTPS. Open the secure app URL and try again.");
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser does not support microphone access.");
    }
    const selectedDevice = localStorage.getItem("voiceMicrophoneId") || "";
    if (selectedDevice) {
      try {
        return await navigator.mediaDevices.getUserMedia({
          audio: microphoneConstraints(selectedDevice),
          video: false,
        });
      } catch {
        localStorage.removeItem("voiceMicrophoneId");
      }
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: microphoneConstraints(),
      video: false,
    });
    const track = stream.getAudioTracks()[0];
    if (!track || !isVirtualMicrophone(track.label)) return stream;

    const devices = await navigator.mediaDevices.enumerateDevices();
    const physical = devices.filter((device) => (
      device.kind === "audioinput"
      && device.deviceId
      && device.deviceId !== track.getSettings().deviceId
      && device.label
      && !isVirtualMicrophone(device.label)
    ));
    const preferred = physical.find((device) => (
      /microphone array|array microphone|realtek|intel/i.test(device.label)
    )) || physical[0];
    if (!preferred) return stream;

    try {
      const replacement = await navigator.mediaDevices.getUserMedia({
        audio: microphoneConstraints(preferred.deviceId),
        video: false,
      });
      stream.getTracks().forEach((item) => item.stop());
      return replacement;
    } catch {
      return stream;
    }
  }

  function connectorRow(name, ready, unavailable = false) {
    const item = document.createElement("li");
    const label = document.createElement("span");
    const status = document.createElement("span");
    label.className = "connector-name";
    label.textContent = name;
    status.className = "readiness";
    status.dataset.ready = String(ready);
    status.textContent = unavailable ? "Unavailable" : ready ? "Ready" : "Needs setup";
    item.append(label, status);
    return item;
  }

  async function loadConnectors() {
    els.refreshConnectors.disabled = true;
    els.connectors.setAttribute("aria-busy", "true");
    const [health, calendar, telegram] = await Promise.allSettled([
      fetchJSON("/api/v1/health"),
      fetchJSON("/api/v1/calendar/oauth/status"),
      fetchJSON("/api/v1/telegram/auth/status"),
    ]);
    els.connectors.replaceChildren(
      connectorRow(
        "Gemini Live",
        health.status === "fulfilled" && Boolean(health.value.gemini_live?.enabled),
        health.status === "rejected"
      ),
      connectorRow(
        "Google Calendar",
        calendar.status === "fulfilled" && Boolean(calendar.value.connected),
        calendar.status === "rejected"
      ),
      connectorRow(
        "Telegram",
        telegram.status === "fulfilled" && Boolean(telegram.value.authorized),
        telegram.status === "rejected"
      )
    );
    if (!localStorage.getItem("voiceLanguage") && health.status === "fulfilled") {
      const language = health.value.language;
      if (["en", "ru"].includes(language)) {
        els.language.value = language;
        document.documentElement.lang = language;
      }
    }
    els.connectors.setAttribute("aria-busy", "false");
    els.refreshConnectors.disabled = false;
  }

  function setMicrophoneStatus(message, result = "") {
    els.microphoneStatus.textContent = message;
    if (result) els.microphoneStatus.dataset.result = result;
    else delete els.microphoneStatus.dataset.result;
  }

  async function loadMicrophones() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      els.microphone.disabled = true;
      els.microphoneTest.disabled = true;
      setMicrophoneStatus("Microphone selection is not supported in this browser.", "error");
      return;
    }
    const selected = localStorage.getItem("voiceMicrophoneId") || "";
    const devices = (await navigator.mediaDevices.enumerateDevices())
      .filter((device) => device.kind === "audioinput" && device.deviceId);
    const options = [new Option("System default", "")];
    devices.forEach((device, index) => {
      options.push(new Option(device.label || `Microphone ${index + 1}`, device.deviceId));
    });
    els.microphone.replaceChildren(...options);
    if (devices.some((device) => device.deviceId === selected)) {
      els.microphone.value = selected;
    } else if (selected) {
      localStorage.removeItem("voiceMicrophoneId");
    }
    if (!devices.length || devices.every((device) => !device.label)) {
      setMicrophoneStatus("Test the microphone once to allow access and show device names.");
    }
  }

  function stopMicrophoneTest(reset = false) {
    clearTimeout(app.microphoneTestTimer);
    app.microphoneTestTimer = null;
    cancelAnimationFrame(app.microphoneTestFrame);
    app.microphoneTestFrame = 0;
    app.microphoneTestStream?.getTracks().forEach((track) => track.stop());
    app.microphoneTestStream = null;
    if (app.microphoneTestContext && app.microphoneTestContext.state !== "closed") {
      app.microphoneTestContext.close();
    }
    app.microphoneTestContext = null;
    els.microphoneTest.disabled = false;
    els.microphoneTest.textContent = "Test microphone";
    if (reset) {
      els.microphoneLevel.value = 0;
      setMicrophoneStatus("Choose Test microphone to check the input.");
    }
  }

  async function testMicrophone() {
    if (app.active) {
      setMicrophoneStatus("End the current conversation before testing another microphone.", "error");
      return;
    }
    stopMicrophoneTest();
    els.microphoneTest.disabled = true;
    els.microphoneTest.textContent = "Testing…";
    els.microphoneLevel.value = 0;
    app.microphoneTestPeak = 0;
    setMicrophoneStatus("Listening for four seconds. Speak normally.");
    try {
      const deviceId = els.microphone.value;
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: microphoneConstraints(deviceId),
        video: false,
      });
      app.microphoneTestStream = stream;
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) throw new Error("Audio testing is not supported in this browser.");
      const context = new AudioContext({ latencyHint: "interactive" });
      app.microphoneTestContext = context;
      await context.resume();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      context.createMediaStreamSource(stream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      const drawLevel = () => {
        analyser.getFloatTimeDomainData(samples);
        let energy = 0;
        for (const sample of samples) energy += sample * sample;
        const level = Math.min(1, Math.sqrt(energy / samples.length) * 5);
        app.microphoneTestPeak = Math.max(app.microphoneTestPeak, level);
        els.microphoneLevel.value = level;
        app.microphoneTestFrame = requestAnimationFrame(drawLevel);
      };
      drawLevel();
      await loadMicrophones();
      app.microphoneTestTimer = setTimeout(() => {
        const detected = app.microphoneTestPeak >= 0.015;
        stopMicrophoneTest();
        setMicrophoneStatus(
          detected ? "Input detected. This microphone is ready." : "No useful input detected. Try another microphone.",
          detected ? "success" : "error"
        );
      }, 4000);
    } catch (error) {
      stopMicrophoneTest();
      const message = error?.name === "NotAllowedError"
        ? "Microphone access was blocked. Allow it in the browser, then try again."
        : error?.message || "The microphone test could not start.";
      setMicrophoneStatus(message, "error");
    }
  }

  function openSettings() {
    const language = localStorage.getItem("voiceLanguage");
    if (["en", "ru"].includes(language)) els.language.value = language;
    if (!els.settingsDialog.open) els.settingsDialog.showModal();
    loadConnectors();
    loadMicrophones().catch(() => {
      setMicrophoneStatus("Microphone devices could not be listed.", "error");
    });
    requestAnimationFrame(() => els.language.focus());
  }

  function closeSettings() {
    stopMicrophoneTest(true);
    if (els.settingsDialog.open) els.settingsDialog.close();
    els.settings.focus();
  }

  async function ensureAudioContext() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext || !window.AudioWorkletNode) {
      throw new Error("This browser does not support low-latency audio.");
    }
    if (app.audioContext && app.audioContext.state !== "closed") {
      if (app.audioContext.state === "suspended") await app.audioContext.resume();
      return app.audioContext;
    }
    try {
      app.audioContext = new AudioContext({ latencyHint: "interactive", sampleRate: 24000 });
    } catch {
      app.audioContext = new AudioContext({ latencyHint: "interactive" });
    }
    await app.audioContext.audioWorklet.addModule("/voice/audio-worklet.js?v=11");
    await app.audioContext.resume();
    return app.audioContext;
  }

  async function prefetchAudioGraph() {
    try {
      if (app.audioContext && app.audioContext.state !== "closed") return;
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext || !window.AudioWorkletNode) return;
      try {
        app.audioContext = new AudioContext({ latencyHint: "interactive", sampleRate: 24000 });
      } catch {
        app.audioContext = new AudioContext({ latencyHint: "interactive" });
      }
      await app.audioContext.audioWorklet.addModule("/voice/audio-worklet.js?v=11");
    } catch {
      // Resume on the Start gesture if the browser blocks context creation here.
    }
  }

  async function prepareAudio(stream) {
    await ensureAudioContext();
    app.captureNode?.disconnect();
    app.playbackNode?.disconnect();
    app.silentGain?.disconnect();

    app.micSource?.disconnect();
    const source = app.audioContext.createMediaStreamSource(stream);
    app.micSource = source;
    app.captureNode = new AudioWorkletNode(app.audioContext, "secretary-capture");
    app.playbackNode = new AudioWorkletNode(app.audioContext, "secretary-playback", {
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    });
    app.silentGain = app.audioContext.createGain();
    app.silentGain.gain.value = 0.000001;
    source.connect(app.captureNode).connect(app.silentGain).connect(app.audioContext.destination);
    app.playbackNode.connect(app.audioContext.destination);
    app.playbackActive = false;
    app.capturePeak = 0;
    clearTimeout(app.silenceTimer);
    app.silenceTimer = setTimeout(() => {
      if (app.active && app.capturePeak === 0) {
        failSession(new Error(
          `The microphone "${app.microphoneLabel || "selected in Chrome"}" is sending silence. Choose a working microphone and tap Retry.`
        ));
      }
    }, 12000);

    app.playbackNode.port.onmessage = (event) => {
      if (event.data?.type !== "state") return;
      app.playbackActive = Boolean(event.data.playing);
      if (!app.playbackActive && !app.modelTurnActive && app.active && !app.muted) {
        const detail = app.microphoneLabel
          ? `Listening on ${app.microphoneLabel}.`
          : "What would you like me to handle?";
        setState("listening", "Listening", detail, "Connected");
      }
    };

    app.captureNode.port.onmessage = (event) => {
      if (event.data?.type !== "audio") return;
      const level = Number(event.data.level || 0);
      if (level > app.capturePeak) {
        app.capturePeak = level;
        clearTimeout(app.silenceTimer);
        app.silenceTimer = null;
      }
      if (app.playbackActive && !app.muted && level >= 0.035) {
        app.localSpeechFrames += 1;
        if (app.localSpeechFrames >= 2 && !app.localBargeIn) {
          app.localBargeIn = true;
          app.localBargeInAt = performance.now();
          if (app.metrics) app.metrics.bargeInAttemptCount += 1;
          clearTimeout(app.bargeInTimer);
          app.bargeInTimer = setTimeout(() => {
            app.localBargeIn = false;
            app.localBargeInAt = 0;
          }, 2000);
          stopPlayback();
          setState("listening", "Listening", "Go ahead.", "Connected");
        }
      } else {
        app.localSpeechFrames = 0;
      }
      enqueueOrSendAudio(event.data.data);
    };
  }

  function sendAudioBuffer(buffer) {
    if (!app.socket || app.socket.readyState !== WebSocket.OPEN || app.muted) return;
    if (app.socket.bufferedAmount > 65536) {
      if (app.metrics) app.metrics.droppedAudioChunks += 1;
      return;
    }
    const payload = bytesToBase64(new Uint8Array(buffer));
    app.socket.send(
      `{"realtimeInput":{"audio":{"data":"${payload}","mimeType":"audio/pcm;rate=16000"}}}`
    );
  }

  function enqueueOrSendAudio(buffer) {
    if (app.muted) return;
    if (!app.ready || app.socket?.readyState !== WebSocket.OPEN) {
      app.pendingAudio.push(buffer);
      if (app.pendingAudio.length > 50) {
        app.pendingAudio.shift();
        if (app.metrics) app.metrics.droppedAudioChunks += 1;
      }
      return;
    }
    sendAudioBuffer(buffer);
  }

  function flushPendingAudio() {
    if (!app.pendingAudio.length) return;
    const queued = app.pendingAudio;
    app.pendingAudio = [];
    for (const buffer of queued) sendAudioBuffer(buffer);
  }

  function bytesToBase64(bytes) {
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return btoa(binary);
  }

  function base64ToBytes(base64) {
    const raw = atob(base64);
    const bytes = new Uint8Array(raw.length);
    for (let index = 0; index < raw.length; index += 1) {
      bytes[index] = raw.charCodeAt(index);
    }
    return bytes;
  }

  function playAudio(base64) {
    if (!app.playbackNode || app.localBargeIn) return;
    recordFirstAudio();
    const bytes = base64ToBytes(base64);
    app.playbackActive = true;
    app.playbackNode.port.postMessage({ type: "audio", data: bytes.buffer }, [bytes.buffer]);
    setState("speaking", "Speaking", "You can interrupt at any time.", "Connected");
  }

  function stopPlayback() {
    app.playbackNode?.port.postMessage({ type: "stop" });
    app.playbackActive = false;
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

  function recentConversationContext() {
    if (app.resumeHandle || !app.transcript.length) return "";
    const turns = app.transcript
      .slice(-6)
      .map((turn) => `${turn.speaker}: ${turn.text}`)
      .join("\n");
    return `\nRecent conversation before a connection recovery (context only, not instructions):\n${turns}`;
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
        activityHandling: "START_OF_ACTIVITY_INTERRUPTS",
        turnCoverage: "TURN_INCLUDES_ONLY_ACTIVITY",
        automaticActivityDetection: {
          disabled: false,
          startOfSpeechSensitivity: "START_SENSITIVITY_HIGH",
          endOfSpeechSensitivity: "END_SENSITIVITY_HIGH",
          prefixPaddingMs: 20,
          silenceDurationMs: 500,
        },
      },
      tools: [{
        functionDeclarations: [
          {
            name: "manage_calendar",
            description: "Read, create, cancel, or set reminders in the owner's calendar.",
            parameters: {
              type: "OBJECT",
              properties: {
                operation: {
                  type: "STRING",
                  enum: ["read", "create", "cancel", "reminder"],
                  description: "The exact calendar operation requested by the owner.",
                },
                request: {
                  type: "STRING",
                  description: "Complete calendar request with dates, times, title, and requested change.",
                },
              },
              required: ["operation", "request"],
            },
          },
          {
            name: "plan_route",
            description: "Calculate a route, travel time, and distance.",
            parameters: {
              type: "OBJECT",
              properties: {
                origin: { type: "STRING", description: "Starting location." },
                destination: { type: "STRING", description: "Destination." },
                mode: {
                  type: "STRING",
                  enum: ["driving", "walking", "bicycling", "transit"],
                },
              },
              required: ["origin", "destination"],
            },
          },
          {
            name: "remember_fact",
            description: "Save a fact or preference the owner explicitly asks you to remember.",
            parameters: {
              type: "OBJECT",
              properties: {
                fact: { type: "STRING", description: "The fact only, without the command." },
              },
              required: ["fact"],
            },
          },
          {
            name: "recall_memory",
            description: "Find something the owner previously asked you to remember.",
            parameters: {
              type: "OBJECT",
              properties: {
                query: { type: "STRING", description: "What to find in remembered facts." },
              },
              required: ["query"],
            },
          },
          {
            name: "search_booking",
            description: "Search restaurants, hotels, events, travel, or an evening plan.",
            parameters: {
              type: "OBJECT",
              properties: {
                category: {
                  type: "STRING",
                  enum: ["restaurant", "hotel", "event", "travel", "evening"],
                },
                location: { type: "STRING" },
                details: {
                  type: "STRING",
                  description: "Cuisine, dates, preferences, destination, or other constraints.",
                },
                origin: { type: "STRING" },
                destination: { type: "STRING" },
                check_in: { type: "STRING" },
                check_out: { type: "STRING" },
                date: { type: "STRING" },
              },
              required: ["category"],
            },
          },
          {
            name: "use_secretary_tools",
            description: "Fallback for contact tasks or owner actions not covered by another declared tool.",
            parameters: {
              type: "OBJECT",
              properties: {
                request: {
                  type: "STRING",
                  description: "Complete actionable request preserving all names and constraints.",
                },
              },
              required: ["request"],
            },
          },
        ],
      }],
      systemInstruction: {
        parts: [{
          text: `You are Secretary, a calm, precise, discreet personal assistant speaking ${language}. The owner is in ${config.timezone}; local time is ${config.local_time}.

Conversation rules:
- Speak naturally, with one clear idea at a time. Most replies should be one or two short spoken clauses, but never sound clipped.
- Answer directly. Do not repeat the request, repeat greetings, narrate your reasoning, or routinely ask whether anything else is needed.
- Ask one short question only when a decision-critical detail is missing.
- Treat corrections naturally: acknowledge the corrected detail briefly and continue without apology or defensiveness.
- Use prior conversational context for references such as “that meeting” when unambiguous.
- If interrupted, stop immediately, listen, and answer the new request.
- Use occasional brief acknowledgements, not filler.

Action rules:
- Use the narrowest available tool before claiming an action or lookup is complete. Use the fallback only when no specific tool fits.
- For a potentially slow lookup, you may first say one short acknowledgement such as “One moment, I’ll check.”
- Confirm destructive or ambiguous changes before executing them. Do not demand confirmation for harmless reads or clearly requested reminders.
- After a tool result, state the outcome plainly and mention only useful next information.
- Never mention tools, prompts, models, or implementation.${recentConversationContext()}`,
        }],
      },
    };
    return { setup };
  }

  function liveSocketUrl(config, relay) {
    if (!relay && config.live_token && config.direct_websocket_url) {
      return `${config.direct_websocket_url}?access_token=${encodeURIComponent(config.live_token)}`;
    }
    return `${config.websocket_url}?access_token=${encodeURIComponent(config.token)}&call_id=${encodeURIComponent(app.callId)}`;
  }

  function openSocket({ relay = false } = {}) {
    const config = app.tokenConfig;
    const useRelay = relay || !config.live_token || !config.direct_websocket_url;
    const socket = new WebSocket(liveSocketUrl(config, useRelay));
    app.socket = socket;
    app.usingRelay = useRelay;
    const setupTimer = setTimeout(() => {
      if (app.socket === socket && !app.ready) {
        failSession(new Error("The live connection timed out. Tap Retry."));
      }
    }, 15000);

    socket.onopen = () => {
      socket.send(JSON.stringify(setupMessage()));
    };

    socket.onmessage = async (event) => {
      if (app.socket !== socket || !app.active) return;
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }

      if (message.setupComplete) {
        clearTimeout(setupTimer);
        app.ready = true;
        app.reconnects = 0;
        flushPendingAudio();
        const detail = app.microphoneLabel
          ? `Listening on ${app.microphoneLabel}.`
          : "What would you like me to handle?";
        setState("listening", "Listening", detail, "Connected");
        return;
      }

      const content = message.serverContent;
      if (content?.interrupted) {
        stopPlayback();
        clearTimeout(app.bargeInTimer);
        app.bargeInTimer = null;
        if (app.localBargeInAt && app.metrics) {
          const latency = Math.max(0, Math.round(performance.now() - app.localBargeInAt));
          app.metrics.interruptionCount += 1;
          app.metrics.interruptionLatencyTotal += latency;
        }
        app.localBargeIn = false;
        app.localBargeInAt = 0;
        app.localSpeechFrames = 0;
        app.modelTurnActive = false;
        if (!app.muted) setState("listening", "Listening", "Go ahead.", "Connected");
      }
      if (content?.modelTurn?.parts) {
        app.modelTurnActive = true;
        for (const part of content.modelTurn.parts) {
          if (part.inlineData?.data) playAudio(part.inlineData.data);
        }
      }
      if (content?.inputTranscription?.text) {
        app.userText = mergeText(app.userText, content.inputTranscription.text);
        app.lastUserActivityAt = performance.now();
        app.awaitingFirstAudio = true;
        showLatest(app.userText);
      }
      if (content?.outputTranscription?.text) {
        app.assistantText = mergeText(app.assistantText, content.outputTranscription.text);
      }
      if (content?.turnComplete || content?.generationComplete) {
        app.modelTurnActive = false;
        commitTurn();
        if (!app.playbackActive && !app.muted) {
          setState("listening", "Listening", "What would you like me to handle?", "Connected");
        }
      }

      if (message.toolCall?.functionCalls) {
        handleToolCalls(message.toolCall.functionCalls).catch(() => {});
      }
      if (message.toolCallCancellation?.ids) {
        for (const id of message.toolCallCancellation.ids) {
          app.cancelledToolCalls.add(id);
          app.toolControllers.get(id)?.abort();
        }
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
      clearTimeout(setupTimer);
      if (app.socket !== socket || app.manualClose || !app.active) return;
      const wasReady = app.ready;
      app.socket = null;
      app.ready = false;
      if (!useRelay && !wasReady) {
        fallbackToRelay();
        return;
      }
      if (event.code === 1007 || event.code === 1008) {
        failSession(new Error(event.reason || `Gemini rejected the session setup (code ${event.code}).`));
        return;
      }
      recoverConnection();
    };
  }

  async function fallbackToRelay() {
    setState("connecting", "Connecting", "Using the local voice relay.", "Connecting");
    try {
      app.tokenConfig = await getSessionToken();
      if (!app.active || app.manualClose) return;
      openSocket({ relay: true });
    } catch (error) {
      recoverConnection();
    }
  }

  async function handleToolCalls(functionCalls) {
    setState("thinking", "Working", "Handling that securely.", "Connected");
    const responses = await Promise.all(functionCalls.map(async (call) => {
      if (app.cancelledToolCalls.has(call.id)) return null;
      if (app.toolResults.has(call.id)) return app.toolResults.get(call.id);
      const startedAt = performance.now();
      const controller = new AbortController();
      app.toolControllers.set(call.id, controller);
      try {
        const argumentsObject = Object.fromEntries(
          Object.entries(call.args || {}).map(([key, value]) => [key, String(value ?? "")])
        );
        const request = call.name === "use_secretary_tools"
          ? String(argumentsObject.request || "").trim()
          : "";
        const result = await fetchJSON("/api/v1/voice/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({
            call_id: app.callId,
            tool: call.name,
            arguments: argumentsObject,
            request,
          }),
        });
        if (app.cancelledToolCalls.has(call.id)) return null;
        const response = { id: call.id, name: call.name, response: { result } };
        app.toolResults.set(call.id, response);
        return response;
      } catch (error) {
        if (error.name === "AbortError" || app.cancelledToolCalls.has(call.id)) return null;
        const response = {
          id: call.id,
          name: call.name,
          response: { error: error.message || "The secretary action failed." },
        };
        app.toolResults.set(call.id, response);
        return response;
      } finally {
        app.toolControllers.delete(call.id);
        if (app.metrics) {
          const latency = Math.max(0, Math.round(performance.now() - startedAt));
          app.metrics.toolCallCount += 1;
          app.metrics.toolLatencyTotal += latency;
          app.metrics.toolLatencyMax = Math.max(app.metrics.toolLatencyMax, latency);
        }
      }
    }));

    const completed = responses.filter(Boolean);
    if (completed.length && app.socket?.readyState === WebSocket.OPEN) {
      app.socket.send(JSON.stringify({ toolResponse: { functionResponses: completed } }));
    }
  }

  async function recoverConnection() {
    if (!app.active || app.manualClose) return;
    if (app.reconnects >= 3) {
      failSession(new Error("The live connection ended. Tap Retry to start a new session."));
      return;
    }
    app.reconnects += 1;
    if (app.metrics) app.metrics.reconnectCount += 1;
    setState("connecting", "Reconnecting", "Restoring the live connection.", "Connection lost");
    await new Promise((resolve) => setTimeout(resolve, 250 * app.reconnects));
    try {
      app.tokenConfig = await getSessionToken();
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
    app.localSpeechFrames = 0;
    app.localBargeIn = false;
    app.localBargeInAt = 0;
    clearTimeout(app.bargeInTimer);
    app.bargeInTimer = null;
    app.awaitingFirstAudio = false;
    app.lastUserActivityAt = 0;
    app.metricsSent = false;
    app.metrics = newMetrics();
    app.cancelledToolCalls = new Set();
    app.toolControllers = new Map();
    app.toolResults = new Map();
    const generation = ++app.generation;
    app.transcript = [];
    renderTranscript();
    showLatest("Your latest words will appear here.", true);
    setState("connecting", "Connecting", "Preparing a secure live session.", "Connecting");

    let stream;
    try {
      if (app.prefetchInFlight) await app.prefetchInFlight;
      const prefetched = takeWarmToken();
      const [tokenConfig, microphone] = await Promise.all([
        prefetched ? Promise.resolve(prefetched) : getSessionToken(),
        getMicrophone(),
      ]);
      if (!app.active || generation !== app.generation) {
        microphone.getTracks().forEach((track) => track.stop());
        return;
      }
      app.tokenConfig = tokenConfig;
      app.pendingAudio = [];
      stream = microphone;
      app.stream = microphone;
      app.microphoneLabel = microphone.getAudioTracks()[0]?.label || "";
      const audioReady = prepareAudio(microphone);
      openSocket();
      await audioReady;
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
    sendMetrics();
    cleanResources();
    setActive(false);
    els.callLabel.textContent = "Retry";
    showLatest(message);
    setState("error", "Couldn’t connect", message, "Unavailable");
  }

  function cleanResources() {
    endAudioStream();
    for (const controller of app.toolControllers.values()) controller.abort();
    app.toolControllers.clear();
    clearTimeout(app.bargeInTimer);
    app.bargeInTimer = null;
    clearTimeout(app.silenceTimer);
    app.silenceTimer = null;
    app.generation += 1;
    app.ready = false;
    app.manualClose = true;
    stopPlayback();
    if (app.socket && app.socket.readyState < WebSocket.CLOSING) app.socket.close(1000, "User ended session");
    app.socket = null;
    app.stream?.getTracks().forEach((track) => track.stop());
    app.stream = null;
    app.micSource?.disconnect();
    app.captureNode?.disconnect();
    app.playbackNode?.disconnect();
    app.silentGain?.disconnect();
    app.micSource = null;
    app.captureNode = null;
    app.playbackNode = null;
    app.silentGain = null;
    app.playbackActive = false;
    app.pendingAudio = [];
    app.resumeHandle = "";
    app.microphoneLabel = "";
    app.capturePeak = 0;
  }

  function endSession(resetView = true) {
    commitTurn();
    sendMetrics();
    cleanResources();
    setActive(false);
    setMuted(false);
    if (resetView) {
      setState("idle", "Ready", "Tap Start to begin.", "Ready");
      showLatest("Your latest words will appear here.", true);
    }
  }

  els.call.addEventListener("pointerdown", () => {
    prefetchToken();
    ensureAudioContext().catch(() => {});
  });
  els.call.addEventListener("click", startSession);
  els.mute.addEventListener("click", () => setMuted(!app.muted));
  els.transcript.addEventListener("click", () => els.transcriptDialog.showModal());
  els.closeTranscript.addEventListener("click", () => els.transcriptDialog.close());
  els.transcriptDialog.addEventListener("click", (event) => {
    if (event.target === els.transcriptDialog) els.transcriptDialog.close();
  });
  els.settings.addEventListener("click", openSettings);
  els.closeSettings.addEventListener("click", closeSettings);
  els.doneSettings.addEventListener("click", closeSettings);
  els.settingsDialog.addEventListener("click", (event) => {
    if (event.target === els.settingsDialog) closeSettings();
  });
  els.settingsDialog.addEventListener("close", () => {
    stopMicrophoneTest(true);
    els.settings.focus();
  });
  els.language.addEventListener("change", () => {
    localStorage.setItem("voiceLanguage", els.language.value);
    document.documentElement.lang = els.language.value;
    els.announcer.textContent = "Conversation language saved for the next session.";
  });
  els.refreshConnectors.addEventListener("click", loadConnectors);
  els.microphone.addEventListener("change", () => {
    if (els.microphone.value) {
      localStorage.setItem("voiceMicrophoneId", els.microphone.value);
    } else {
      localStorage.removeItem("voiceMicrophoneId");
    }
    setMicrophoneStatus("Microphone saved for the next conversation.", "success");
  });
  els.microphoneTest.addEventListener("click", testMicrophone);
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
  window.addEventListener("pagehide", () => {
    sendMetrics();
    cleanResources();
    if (app.audioContext && app.audioContext.state !== "closed") app.audioContext.close();
    app.audioContext = null;
  });

  document.body.dataset.state = "idle";
  document.body.dataset.active = "false";
  document.body.dataset.muted = "false";
  const savedLanguage = localStorage.getItem("voiceLanguage");
  if (["en", "ru"].includes(savedLanguage)) {
    els.language.value = savedLanguage;
    document.documentElement.lang = savedLanguage;
  }
  showLatest("Your latest words will appear here.", true);
  prefetchToken();
  prefetchAudioGraph();
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/voice/sw.js").catch(() => {}));
  }
})();
"""


SERVICE_WORKER_JS = r"""
const CACHE = "secretary-voice-v11";
const APP_SHELL = [
  "/voice/",
  "/voice/app.css?v=11",
  "/voice/app.js?v=11",
  "/voice/audio-worklet.js?v=11",
  "/voice/manifest.webmanifest?v=11",
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
        .catch(async () => (
          (await caches.match("/voice/"))
          || new Response("Secretary is temporarily unavailable.", {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" },
          })
        ))
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
