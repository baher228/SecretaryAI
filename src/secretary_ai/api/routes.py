import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel as _BaseModel

from secretary_ai.domain.models import (
    AgentLiveRespondRequest,
    AgentLiveRespondResponse,
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    AgentReplyRequest,
    AgentReplyResponse,
    ArchitectureOverview,
    BookingSearchRequest,
    BookingSearchResponse,
    CalendarCacheResponse,
    CalendarProcessResponse,
    CalendarQueueRequest,
    CalendarQueueResponse,
    CalendarQueueSnapshotResponse,
    CallAudioPlayRequest,
    CallAudioRecordRequest,
    CallAudioResponse,
    CallEventAck,
    CallTranscriptRequest,
    ChatRequest,
    ChatResponse,
    InboundCallResponse,
    MapRouteRequest,
    MapRouteResponse,
    ModelCheckRequest,
    ModelCheckResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PostCallEventRequest,
    PostCallSummary,
    TelegramAuthSendCodeRequest,
    TelegramAuthSendCodeResponse,
    TelegramAuthSignInRequest,
    TelegramAuthSignInResponse,
    TelegramLiveAgentResponse,
    TelegramLiveAgentStartRequest,
    TelegramLiveAgentStatusResponse,
    TelegramAuthStatusResponse,
)
from secretary_ai.services.secretary import SecretaryService

router = APIRouter()


def get_secretary(request: Request) -> SecretaryService:
    return request.app.state.secretary  # type: ignore[no-any-return]


def _ws_event(
    event_type: str,
    call_id: str,
    detail: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "call_id": call_id,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }


@router.get("/health")
async def health(
    secretary: SecretaryService = Depends(get_secretary),
) -> dict[str, Any]:
    s = secretary.settings
    tg_ready, tg_detail = secretary.telegram.readiness()
    cal_ready, cal_detail = secretary.calendar.readiness()
    return {
        "status": "ok",
        "version": "0.1.0",
        "mode": "telegram_mtproto_mvp",
        "language": s.language,
        "openai": {
            "configured": bool(s.openai_api_key),
            "model": s.openai_model,
        },
        "gemini_live": {
            "enabled": bool(s.gemini_live_enabled and s.gemini_api_key),
            "model": s.gemini_live_model,
            "voice": s.gemini_live_voice,
        },
        "telegram": {
            "ready": tg_ready,
            "detail": tg_detail,
            "active_calls": len(secretary.live_sessions),
        },
        "calendar": {
            "ready": cal_ready,
            "detail": cal_detail,
        },
    }


@router.get("/version")
async def version() -> dict[str, str]:
    return {"version": "0.1.0", "name": "Secretary AI"}


@router.get("/debug/logs")
async def debug_logs(
    lines: int = Query(50, ge=1, le=500),
    secretary: SecretaryService = Depends(get_secretary),
) -> list[dict[str, Any]]:
    """Tail the live debug JSONL log file."""
    log_path = Path(secretary.settings.telegram_live_debug_log_path)
    if not log_path.exists():
        return []
    try:
        raw_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        tail = raw_lines[-lines:]
        result = []
        for line in tail:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result
    except Exception:
        return []


@router.websocket("/debug/ws")
async def debug_ws(
    websocket: WebSocket,
) -> None:
    """Stream live debug log entries over WebSocket."""
    await websocket.accept()
    secretary: SecretaryService = websocket.app.state.secretary
    log_path = Path(secretary.settings.telegram_live_debug_log_path)
    last_size = log_path.stat().st_size if log_path.exists() else 0

    try:
        while True:
            await asyncio.sleep(1.0)
            if not log_path.exists():
                last_size = 0
                continue
            current_size = log_path.stat().st_size
            if current_size == last_size:
                continue
            if current_size < last_size:
                last_size = 0
            with log_path.open("rb") as f:
                f.seek(last_size)
                new_data = f.read().decode("utf-8", errors="replace")
            last_size = current_size
            for line in new_data.strip().splitlines():
                try:
                    entry = json.loads(line)
                    await websocket.send_json(entry)
                except (json.JSONDecodeError, Exception):
                    continue
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.get("/architecture", response_model=ArchitectureOverview)
async def architecture(secretary: SecretaryService = Depends(get_secretary)) -> ArchitectureOverview:
    return secretary.architecture_overview()


@router.post("/model/check", response_model=ModelCheckResponse)
async def check_model(
    payload: ModelCheckRequest, secretary: SecretaryService = Depends(get_secretary)
) -> ModelCheckResponse:
    return await secretary.check_model_connection(prompt=payload.prompt)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, secretary: SecretaryService = Depends(get_secretary)
) -> ChatResponse:
    return await secretary.chat_direct(payload)


@router.post("/maps/route", response_model=MapRouteResponse)
async def maps_route(
    payload: MapRouteRequest, secretary: SecretaryService = Depends(get_secretary)
) -> MapRouteResponse:
    return await secretary.map_route(payload)


@router.get("/telegram/auth/status", response_model=TelegramAuthStatusResponse)
async def telegram_auth_status(
    secretary: SecretaryService = Depends(get_secretary),
) -> TelegramAuthStatusResponse:
    return await secretary.telegram_auth_status()


@router.post("/telegram/auth/send-code", response_model=TelegramAuthSendCodeResponse)
async def telegram_auth_send_code(
    payload: TelegramAuthSendCodeRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> TelegramAuthSendCodeResponse:
    return await secretary.telegram_send_code(phone_number=payload.phone_number)


@router.post("/telegram/auth/sign-in", response_model=TelegramAuthSignInResponse)
async def telegram_auth_sign_in(
    payload: TelegramAuthSignInRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> TelegramAuthSignInResponse:
    return await secretary.telegram_sign_in(
        phone_number=payload.phone_number,
        code=payload.code,
        phone_code_hash=payload.phone_code_hash,
        password=payload.password,
    )


@router.post("/calls/outbound", response_model=OutboundCallResponse)
async def start_outbound_call(
    payload: OutboundCallRequest, secretary: SecretaryService = Depends(get_secretary)
) -> OutboundCallResponse:
    return await secretary.start_outbound_call(payload)


@router.post("/calls/{call_id}/transcript", response_model=InboundCallResponse)
async def append_call_transcript(
    call_id: str,
    payload: CallTranscriptRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> InboundCallResponse:
    return await secretary.append_transcript(call_id, payload)


@router.post("/calls/post-call", response_model=PostCallSummary)
async def finalize_call(
    payload: PostCallEventRequest, secretary: SecretaryService = Depends(get_secretary)
) -> PostCallSummary:
    return await secretary.finalize_call(payload)


@router.post("/agent/reply", response_model=AgentReplyResponse)
async def agent_reply(
    payload: AgentReplyRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> AgentReplyResponse:
    return await secretary.generate_agent_reply(
        call_id=payload.call_id,
        transcript=payload.transcript,
        context=payload.context,
    )


@router.post("/agent/analyze", response_model=AgentAnalyzeResponse)
async def agent_analyze(
    payload: AgentAnalyzeRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> AgentAnalyzeResponse:
    return await secretary.analyze_agent_turn(
        call_id=payload.call_id,
        transcript=payload.transcript,
        context=payload.context,
    )


@router.post("/agent/live/respond", response_model=AgentLiveRespondResponse)
async def agent_live_respond(
    payload: AgentLiveRespondRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> AgentLiveRespondResponse:
    return await secretary.live_agent_respond(
        call_id=payload.call_id,
        transcript=payload.transcript,
        context=payload.context,
        speak_response=payload.speak_response,
    )


@router.post("/calls/{call_id}/hangup", response_model=CallEventAck)
async def end_call(call_id: str, secretary: SecretaryService = Depends(get_secretary)) -> CallEventAck:
    result = await secretary.end_call(call_id)
    if result.status == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.detail)
    return result


@router.post("/calls/{call_id}/audio/play", response_model=CallAudioResponse)
async def stream_audio_out(
    call_id: str,
    payload: CallAudioPlayRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> CallAudioResponse:
    result = await secretary.stream_audio_out(call_id, payload)
    if result.status == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.detail)
    return result


@router.post("/calls/{call_id}/audio/record", response_model=CallAudioResponse)
async def stream_audio_in(
    call_id: str,
    payload: CallAudioRecordRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> CallAudioResponse:
    result = await secretary.stream_audio_in(call_id, payload)
    if result.status == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.detail)
    return result


@router.post("/calls/{call_id}/live/start", response_model=TelegramLiveAgentResponse)
async def start_telegram_live_agent(
    call_id: str,
    payload: TelegramLiveAgentStartRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> TelegramLiveAgentResponse:
    result = await secretary.start_telegram_live_agent(call_id, payload)
    if result.status == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.detail)
    return result


@router.post("/calls/{call_id}/live/stop", response_model=TelegramLiveAgentResponse)
async def stop_telegram_live_agent(
    call_id: str,
    secretary: SecretaryService = Depends(get_secretary),
) -> TelegramLiveAgentResponse:
    return await secretary.stop_telegram_live_agent(call_id)


@router.get("/calls/{call_id}/live/status", response_model=TelegramLiveAgentStatusResponse)
async def get_telegram_live_agent_status(
    call_id: str,
    secretary: SecretaryService = Depends(get_secretary),
) -> TelegramLiveAgentStatusResponse:
    return await secretary.telegram_live_agent_status(call_id)


@router.get("/calls/readiness")
async def calls_readiness(secretary: SecretaryService = Depends(get_secretary)) -> dict:
    return await secretary.calls_readiness()


@router.get("/calendar/cache", response_model=CalendarCacheResponse)
async def calendar_cache(
    limit: int = Query(default=10, ge=1, le=100),
    secretary: SecretaryService = Depends(get_secretary),
) -> CalendarCacheResponse:
    return await secretary.calendar_cache(limit=limit)


@router.get("/calendar/queue", response_model=CalendarQueueSnapshotResponse)
async def calendar_queue(
    limit: int = Query(default=20, ge=1, le=200),
    secretary: SecretaryService = Depends(get_secretary),
) -> CalendarQueueSnapshotResponse:
    return await secretary.calendar_queue(limit=limit)


@router.post("/calendar/queue", response_model=CalendarQueueResponse)
async def calendar_enqueue(
    payload: CalendarQueueRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> CalendarQueueResponse:
    return await secretary.calendar_enqueue(payload)


@router.post("/calendar/process", response_model=CalendarProcessResponse)
async def calendar_process(
    max_items: int = Query(default=5, ge=1, le=50),
    secretary: SecretaryService = Depends(get_secretary),
) -> CalendarProcessResponse:
    return await secretary.calendar_process(max_items=max_items)


@router.post("/calendar/refresh")
async def calendar_refresh(
    days: int = Query(default=7, ge=1, le=60),
    max_results: int = Query(default=30, ge=1, le=200),
    secretary: SecretaryService = Depends(get_secretary),
) -> dict:
    return await secretary.calendar_refresh(days=days, max_results=max_results)


# --- Booking search endpoints ---


@router.post("/booking/search", response_model=BookingSearchResponse)
async def booking_search(
    payload: BookingSearchRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> BookingSearchResponse:
    """Search for restaurants, hotels, events, or travel options."""
    result = await secretary.booking.search_by_action(
        action=payload.booking_type,
        payload=str(payload.query_params.get("preferences", "")),
        extracted={**payload.query_params, "location": payload.location},
    )
    return BookingSearchResponse(
        call_id=payload.call_id,
        status="ok",
        results=result.get("results") or [],
        voice_summary=result.get("voice_summary"),
        category=result.get("category"),
    )


@router.get("/booking/last-results")
async def booking_last_results(
    secretary: SecretaryService = Depends(get_secretary),
) -> dict:
    """Return the most recent booking search results."""
    return secretary.booking.last_results


# --- Wake word endpoints ---


@router.get("/wake-word/actions")
async def wake_word_actions(
    secretary: SecretaryService = Depends(get_secretary),
) -> list[dict]:
    """List all registered wake-word actions and their trigger phrases."""
    return secretary.wake_word.list_actions()


class WakeWordDetectRequest(_BaseModel):
    transcript: str


@router.post("/wake-word/detect")
async def wake_word_detect(
    body: WakeWordDetectRequest | None = None,
    transcript: str = Query(None, description="Text to scan for wake-word triggers"),
    secretary: SecretaryService = Depends(get_secretary),
) -> dict:
    """Test wake-word detection against a transcript (JSON body or query param)."""
    text = (body.transcript if body else None) or transcript or ""
    match = secretary.wake_word.detect(text)
    if match is None:
        return {"detected": False}
    return {"detected": True, **match.to_dict()}


# ---------------------------------------------------------------------------
# Voice / TTS settings
# ---------------------------------------------------------------------------

@router.get("/voice/providers")
async def voice_providers(
    secretary: SecretaryService = Depends(get_secretary),
) -> dict[str, Any]:
    """List available TTS providers and current configuration."""
    from secretary_ai.core.locales import SILERO_VOICES
    from secretary_ai.services.tts import TTSEngine

    s = secretary.settings
    return {
        "current_provider": s.tts_provider,
        "available_providers": TTSEngine.available_providers(),
        "edge_tts": {
            "voice": s.tts_voice,
            "rate": s.tts_rate,
            "volume": s.tts_volume,
        },
        "silero": {
            "model_id": s.tts_silero_model_id,
            "speaker": s.tts_silero_speaker,
            "sample_rate": s.tts_silero_sample_rate,
            "device": s.tts_silero_device,
            "available_voices": SILERO_VOICES,
        },
    }


@router.get("/voice/silero/voices")
async def silero_voices() -> dict[str, list[dict[str, str]]]:
    """List all available Silero voice speakers by language."""
    from secretary_ai.core.locales import SILERO_VOICES

    return SILERO_VOICES


@router.get("/calendar/oauth/authorize")
async def calendar_oauth_authorize(
    secretary: SecretaryService = Depends(get_secretary),
) -> RedirectResponse:
    """Redirect the user to Google's OAuth consent screen."""
    url = secretary.calendar.get_oauth_authorize_url()
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env",
        )
    return RedirectResponse(url)


@router.get("/calendar/oauth/callback")
async def calendar_oauth_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state: str | None = Query(default=None),
    secretary: SecretaryService = Depends(get_secretary),
) -> HTMLResponse:
    """Handle the OAuth callback from Google and store the token."""
    if error or not code:
        detail = error or "No authorization code received."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authorization failed: {detail}",
        )
    result = await asyncio.to_thread(secretary.calendar.handle_oauth_callback, code, state)
    if result.get("status") == "ok":
        html = (
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h1>&#10003; Google Calendar Connected</h1>"
            "<p>You can close this tab and return to Secretary AI.</p>"
            "</body></html>"
        )
        return HTMLResponse(content=html)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=result.get("detail", "OAuth callback failed."),
    )


@router.get("/calendar/oauth/status")
async def calendar_oauth_status(
    secretary: SecretaryService = Depends(get_secretary),
) -> dict:
    """Check whether a valid OAuth token is stored."""
    ready, detail = secretary.calendar.readiness()
    return {"connected": ready, "detail": detail}


# ─── Contacts ─────────────────────────────────────────────────────


@router.get("/contacts")
async def list_contacts(
    secretary: SecretaryService = Depends(get_secretary),
) -> list[dict]:
    """Return all contacts sorted by most recently called."""
    return secretary.contacts.list_all()


@router.get("/contacts/{caller_id}")
async def get_contact(
    caller_id: str,
    secretary: SecretaryService = Depends(get_secretary),
) -> dict:
    """Return a single contact by caller ID."""
    contact = secretary.contacts.get(caller_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return contact


class ContactUpsertRequest(_BaseModel):
    name: str | None = None
    language: str | None = None
    notes: str | None = None


@router.put("/contacts/{caller_id}")
async def upsert_contact(
    caller_id: str,
    body: ContactUpsertRequest,
    secretary: SecretaryService = Depends(get_secretary),
) -> dict:
    """Create or update a contact."""
    return secretary.contacts.upsert(
        caller_id,
        name=body.name,
        language=body.language,
        notes=body.notes,
    )


@router.delete("/contacts/{caller_id}")
async def delete_contact(
    caller_id: str,
    secretary: SecretaryService = Depends(get_secretary),
) -> dict:
    """Delete a contact."""
    deleted = secretary.contacts.delete(caller_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return {"deleted": True, "caller_id": caller_id}


@router.get("/calls")
async def list_calls(secretary: SecretaryService = Depends(get_secretary)) -> list[dict]:
    return await secretary.list_calls()


@router.get("/calls/events")
async def list_call_events(
    limit: int = Query(default=50, ge=1, le=500),
    secretary: SecretaryService = Depends(get_secretary),
) -> list[dict]:
    return await secretary.list_call_events(limit)


@router.get("/calls/{call_id}")
async def get_call(call_id: str, secretary: SecretaryService = Depends(get_secretary)) -> dict:
    record = await secretary.get_call(call_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="call not found")
    return record


@router.websocket("/ws/live/{call_id}")
async def websocket_live_agent(websocket: WebSocket, call_id: str) -> None:
    await websocket.accept()
    secretary: SecretaryService = websocket.app.state.secretary
    await websocket.send_json(
        _ws_event(
            event_type="connected",
            call_id=call_id,
            detail="Live socket connected. Send type=transcript to trigger AI response.",
            data={"supported_types": ["ping", "transcript", "hangup", "get_call"]},
        )
    )

    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            break
        except Exception:
            await websocket.send_json(
                _ws_event(
                    event_type="error",
                    call_id=call_id,
                    detail="Expected JSON message payload.",
                )
            )
            continue

        message_type = str(payload.get("type", "")).strip().lower()

        if message_type == "ping":
            await websocket.send_json(_ws_event("pong", call_id, "ok"))
            continue

        if message_type == "get_call":
            call_record = await secretary.get_call(call_id)
            if call_record is None:
                await websocket.send_json(
                    _ws_event("call_state", call_id, "Call not found.", {"status": "not_found"})
                )
            else:
                await websocket.send_json(
                    _ws_event("call_state", call_id, "Call record fetched.", call_record)
                )
            continue

        if message_type == "hangup":
            ack = await secretary.end_call(call_id)
            await websocket.send_json(
                _ws_event("hangup_ack", call_id, ack.detail, data=ack.model_dump())
            )
            continue

        if message_type == "transcript":
            transcript = str(payload.get("transcript", "")).strip()
            if not transcript:
                await websocket.send_json(
                    _ws_event(
                        event_type="error",
                        call_id=call_id,
                        detail="Missing transcript for type=transcript.",
                    )
                )
                continue

            raw_context = payload.get("context", {})
            context = raw_context if isinstance(raw_context, dict) else {}
            speak_response = bool(payload.get("speak_response", True))

            response = await secretary.live_agent_respond(
                call_id=call_id,
                transcript=transcript,
                context=context,
                speak_response=speak_response,
            )
            await websocket.send_json(
                _ws_event(
                    event_type="agent_response",
                    call_id=call_id,
                    detail="AI response generated.",
                    data=response.model_dump(),
                )
            )
            continue

        await websocket.send_json(
            _ws_event(
                event_type="error",
                call_id=call_id,
                detail=(
                    "Unknown message type. Supported: ping, transcript, hangup, get_call."
                ),
            )
        )
