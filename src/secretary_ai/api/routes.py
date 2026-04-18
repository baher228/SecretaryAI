from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status

from secretary_ai.domain.models import (
    AgentLiveRespondRequest,
    AgentLiveRespondResponse,
    AgentAnalyzeRequest,
    AgentAnalyzeResponse,
    AgentReplyRequest,
    AgentReplyResponse,
    ArchitectureOverview,
    CallAudioPlayRequest,
    CallAudioRecordRequest,
    CallAudioResponse,
    CallEventAck,
    CallTranscriptRequest,
    ChatRequest,
    ChatResponse,
    InboundCallResponse,
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
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "telegram_mtproto_mvp"}


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
