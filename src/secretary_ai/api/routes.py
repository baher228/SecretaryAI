from fastapi import APIRouter, Depends, HTTPException, Request, status

from secretary_ai.domain.models import (
    ArchitectureOverview,
    InboundCallRequest,
    InboundCallResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PostCallEventRequest,
    PostCallSummary,
)
from secretary_ai.services.secretary import SecretaryService

router = APIRouter()


def get_secretary(request: Request) -> SecretaryService:
    return request.app.state.secretary  # type: ignore[no-any-return]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "scaffold_only"}


@router.get("/architecture", response_model=ArchitectureOverview)
async def architecture(secretary: SecretaryService = Depends(get_secretary)) -> ArchitectureOverview:
    return secretary.architecture_overview()


@router.post("/calls/inbound", response_model=InboundCallResponse)
async def handle_inbound_call(
    payload: InboundCallRequest, secretary: SecretaryService = Depends(get_secretary)
) -> InboundCallResponse:
    try:
        return await secretary.handle_inbound_call(payload)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc


@router.post("/calls/outbound", response_model=OutboundCallResponse)
async def start_outbound_call(
    payload: OutboundCallRequest, secretary: SecretaryService = Depends(get_secretary)
) -> OutboundCallResponse:
    try:
        return await secretary.start_outbound_call(payload)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc


@router.post("/calls/post-call", response_model=PostCallSummary)
async def finalize_call(
    payload: PostCallEventRequest, secretary: SecretaryService = Depends(get_secretary)
) -> PostCallSummary:
    try:
        return await secretary.finalize_call(payload)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc


@router.get("/calls/{call_id}")
async def get_call(call_id: str, secretary: SecretaryService = Depends(get_secretary)) -> dict:
    try:
        return await secretary.get_call(call_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
