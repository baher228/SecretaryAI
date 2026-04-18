from datetime import datetime, timezone
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


class InboundCallRequest(BaseModel):
    call_id: str
    from_number: str
    to_number: str | None = None
    transcript: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundCallResponse(BaseModel):
    call_id: str
    status: str = "not_implemented"
    detail: str = "Inbound call workflow is not implemented yet."


class OutboundCallRequest(BaseModel):
    to_number: str
    message: str
    purpose: OutboundPurpose
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutboundCallResponse(BaseModel):
    call_id: str
    status: str = "not_implemented"
    detail: str = "Outbound call workflow is not implemented yet."


class PostCallEventRequest(BaseModel):
    call_id: str
    transcript: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostCallSummary(BaseModel):
    call_id: str
    status: str = "not_implemented"
    detail: str = "Post-call summary workflow is not implemented yet."


class ArchitectureOverview(BaseModel):
    name: str
    mode: str
    components: list[str]
    notes: str
