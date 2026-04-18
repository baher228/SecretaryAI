from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from secretary_ai.domain.models import (
    AgentReplyRequest,
    AgentReplyResponse,
    ArchitectureOverview,
    CallAudioPlayRequest,
    CallAudioRecordRequest,
    CallAudioResponse,
    CallEventAck,
    CallTranscriptRequest,
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
    TelegramAuthStatusResponse,
)
from secretary_ai.services.secretary import SecretaryService

router = APIRouter()


def get_secretary(request: Request) -> SecretaryService:
    return request.app.state.secretary  # type: ignore[no-any-return]


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
