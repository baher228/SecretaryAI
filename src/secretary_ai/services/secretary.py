import httpx

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import (
    ArchitectureOverview,
    InboundCallRequest,
    InboundCallResponse,
    ModelCheckResponse,
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
                "GLM Client (Z.AI, implemented)",
                "Intent Engine (planned)",
                "Telephony Adapter (planned)",
                "Calendar Adapter (planned)",
                "Notification Dispatcher (planned)",
                "Storage Layer (planned)",
            ],
            notes=(
                "Endpoints and contracts are in place. "
                "GLM connection check is implemented; call workflows remain TODO."
            ),
        )

    async def check_model_connection(self, prompt: str) -> ModelCheckResponse:
        if not self.settings.zai_api_key:
            return ModelCheckResponse(
                model=self.settings.zai_model,
                connected=False,
                detail="Missing ZAI_API_KEY in environment.",
            )

        base_url = self.settings.zai_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": self.settings.zai_model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 80,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.zai_api_key}",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en",
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.zai_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 300:
                return ModelCheckResponse(
                    model=self.settings.zai_model,
                    connected=False,
                    detail=f"GLM request failed ({response.status_code}).",
                    output=response.text[:200],
                )
            data = response.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content")
            )
            if not isinstance(text, str):
                text = None
            return ModelCheckResponse(
                model=self.settings.zai_model,
                connected=True,
                detail="Connected to Z.AI GLM successfully.",
                output=text,
            )
        except Exception as exc:
            return ModelCheckResponse(
                model=self.settings.zai_model,
                connected=False,
                detail=f"Connection error: {exc.__class__.__name__}",
            )

    async def handle_inbound_call(self, payload: InboundCallRequest) -> InboundCallResponse:
        raise NotImplementedError("Inbound call workflow is not implemented yet.")

    async def start_outbound_call(self, payload: OutboundCallRequest) -> OutboundCallResponse:
        raise NotImplementedError("Outbound call workflow is not implemented yet.")

    async def finalize_call(self, payload: PostCallEventRequest) -> PostCallSummary:
        raise NotImplementedError("Post-call workflow is not implemented yet.")

    async def get_call(self, call_id: str) -> dict:
        raise NotImplementedError("Call storage/query workflow is not implemented yet.")
