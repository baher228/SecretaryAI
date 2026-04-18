from secretary_ai.core.config import Settings
from secretary_ai.domain.models import (
    ArchitectureOverview,
    InboundCallRequest,
    InboundCallResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PostCallEventRequest,
    PostCallSummary,
)


class SecretaryService:
    """
    Architecture-only scaffold.
    Business logic is intentionally deferred for hackathon iteration speed.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def architecture_overview(self) -> ArchitectureOverview:
        return ArchitectureOverview(
            name="Secretary AI",
            mode="scaffold_only",
            components=[
                "API Layer (FastAPI routes)",
                "Orchestrator (SecretaryService)",
                "Intent Engine (planned)",
                "Telephony Adapter (planned)",
                "Calendar Adapter (planned)",
                "Notification Dispatcher (planned)",
                "Storage Layer (planned)",
            ],
            notes=(
                "Endpoints and contracts are in place. "
                "Integrations and workflow implementation are TODO."
            ),
        )

    async def handle_inbound_call(self, payload: InboundCallRequest) -> InboundCallResponse:
        raise NotImplementedError("Inbound call workflow is not implemented yet.")

    async def start_outbound_call(self, payload: OutboundCallRequest) -> OutboundCallResponse:
        raise NotImplementedError("Outbound call workflow is not implemented yet.")

    async def finalize_call(self, payload: PostCallEventRequest) -> PostCallSummary:
        raise NotImplementedError("Post-call workflow is not implemented yet.")

    async def get_call(self, call_id: str) -> dict:
        raise NotImplementedError("Call storage/query workflow is not implemented yet.")
