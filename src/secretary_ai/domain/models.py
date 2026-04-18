from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    BOOK_EVENT = "book_event"
    RESCHEDULE_EVENT = "reschedule_event"
    CANCEL_EVENT = "cancel_event"
    REMINDER = "reminder"
    CONFIRMATION = "confirmation"
    FOLLOW_UP = "follow_up"
    TRANSFER_HUMAN = "transfer_human"
    LEAVE_MESSAGE = "leave_message"
    GENERAL_QUERY = "general_query"
    UNKNOWN = "unknown"


class OutboundPurpose(str, Enum):
    REMINDER = "reminder"
    CONFIRMATION = "confirmation"
    FOLLOW_UP = "follow_up"


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallTranscriptRequest(BaseModel):
    transcript: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundCallResponse(BaseModel):
    call_id: str
    direction: CallDirection = CallDirection.INBOUND
    status: str
    detail: str


class OutboundCallRequest(BaseModel):
    target_user: str = Field(description="Telegram username (@name) or numeric user id as string.")
    purpose: OutboundPurpose = OutboundPurpose.REMINDER
    initial_audio_path: str | None = Field(
        default=None,
        description="Optional local audio file path to stream into the call immediately.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutboundCallResponse(BaseModel):
    call_id: str
    status: str
    detail: str
    provider: str = "telegram_mtproto"
    chat_id: int | None = None


class CallAudioPlayRequest(BaseModel):
    audio_path: str


class CallAudioRecordRequest(BaseModel):
    output_path: str


class CallAudioResponse(BaseModel):
    call_id: str
    status: str
    detail: str


class TelegramLiveAgentStartRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    speak_response: bool = True


class TelegramLiveAgentResponse(BaseModel):
    call_id: str
    status: str
    detail: str
    recording_path: str | None = None
    stt_status: str | None = None
    speak_response: bool = True


class TelegramLiveAgentStatusResponse(BaseModel):
    call_id: str
    running: bool
    status: str
    detail: str
    recording_path: str | None = None
    last_stt_status: str | None = None
    last_transcript: str | None = None


class PostCallEventRequest(BaseModel):
    call_id: str
    transcript: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostCallSummary(BaseModel):
    call_id: str
    status: str
    detail: str


class ArchitectureOverview(BaseModel):
    name: str
    mode: str
    components: list[str]
    notes: str


class ModelCheckRequest(BaseModel):
    prompt: str = "Reply with: connection_ok"


class ModelCheckResponse(BaseModel):
    provider: str = "z.ai"
    model: str
    connected: bool
    detail: str
    output: str | None = None


class TelegramAuthSendCodeRequest(BaseModel):
    phone_number: str


class TelegramAuthSendCodeResponse(BaseModel):
    status: str
    phone_number: str
    phone_code_hash: str | None = None
    detail: str


class TelegramAuthSignInRequest(BaseModel):
    phone_number: str
    code: str | None = None
    phone_code_hash: str | None = None
    password: str | None = None


class TelegramAuthStatusResponse(BaseModel):
    connected: bool
    authorized: bool
    detail: str
    session_path: str


class TelegramAuthSignInResponse(BaseModel):
    status: str
    authorized: bool
    detail: str


class CallEventAck(BaseModel):
    status: str
    detail: str


class AgentReplyRequest(BaseModel):
    call_id: str
    transcript: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentReplyResponse(BaseModel):
    call_id: str
    reply: str
    action_items: list[str] = Field(default_factory=list)


class AgentAnalyzeRequest(BaseModel):
    call_id: str
    transcript: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentAnalyzeResponse(BaseModel):
    call_id: str
    intent: IntentType = IntentType.UNKNOWN
    confidence: float = 0.0
    reply: str
    requires_human: bool = False
    transfer_reason: str | None = None
    action_items: list[str] = Field(default_factory=list)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    model: str


class AgentLiveRespondRequest(BaseModel):
    call_id: str
    transcript: str
    context: dict[str, Any] = Field(default_factory=dict)
    speak_response: bool = True


class AgentLiveRespondResponse(BaseModel):
    call_id: str
    transcript: str
    reply: str
    intent: IntentType
    confidence: float
    requires_human: bool
    transfer_reason: str | None = None
    action_items: list[str] = Field(default_factory=list)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    model: str
    tts_audio_path: str | None = None
    tts_status: str | None = None
    call_audio_status: str | None = None
