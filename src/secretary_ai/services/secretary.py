import json
from typing import Any

import httpx

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import (
    AgentReplyResponse,
    ArchitectureOverview,
    CallAudioPlayRequest,
    CallAudioRecordRequest,
    CallAudioResponse,
    CallEventAck,
    CallTranscriptRequest,
    InboundCallResponse,
    ModelCheckResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PostCallEventRequest,
    PostCallSummary,
    TelegramAuthSendCodeResponse,
    TelegramAuthSignInResponse,
    TelegramAuthStatusResponse,
)
from secretary_ai.services.telegram_calls import TelegramCallService


class SecretaryService:
    """Main orchestrator: Z.AI reasoning + Telegram MTProto call provider."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.telegram = TelegramCallService(settings)

    async def startup(self) -> None:
        await self.telegram.start()

    async def shutdown(self) -> None:
        await self.telegram.stop()

    def architecture_overview(self) -> ArchitectureOverview:
        return ArchitectureOverview(
            name="Secretary AI",
            mode="telegram_mtproto_mvp",
            components=[
                "API Layer (FastAPI routes)",
                "Telegram MTProto (Telethon user session)",
                "Telegram Calls Engine (py-tgcalls private calls)",
                "Secretary Orchestrator (this service)",
                "Z.AI Reasoning Endpoint",
                "Storage Layer (in-memory MVP)",
            ],
            notes=(
                "Experimental hackathon stack using a real Telegram user account session. "
                "Designed for easy provider swap to Twilio/others later."
            ),
        )

    async def check_model_connection(self, prompt: str) -> ModelCheckResponse:
        if not self.settings.zai_api_key:
            return ModelCheckResponse(
                model=self.settings.zai_model,
                connected=False,
                detail="Missing ZAI_API_KEY in environment.",
            )
        payload = {
            "model": self.settings.zai_model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 100,
        }
        result = await self._zai_chat_completion(payload)
        if result.get("error"):
            return ModelCheckResponse(
                model=self.settings.zai_model,
                connected=False,
                detail=result["error"],
                output=result.get("raw"),
            )
        message = self._extract_message(result["data"])
        return ModelCheckResponse(
            model=self.settings.zai_model,
            connected=True,
            detail="Connected to Z.AI GLM successfully.",
            output=message.get("content"),
        )

    async def telegram_auth_status(self) -> TelegramAuthStatusResponse:
        payload = await self.telegram.auth_status()
        return TelegramAuthStatusResponse(**payload)

    async def telegram_send_code(self, phone_number: str) -> TelegramAuthSendCodeResponse:
        payload = await self.telegram.send_code(phone_number)
        return TelegramAuthSendCodeResponse(**payload)

    async def telegram_sign_in(
        self,
        phone_number: str,
        code: str | None,
        phone_code_hash: str | None,
        password: str | None,
    ) -> TelegramAuthSignInResponse:
        payload = await self.telegram.sign_in(
            phone_number=phone_number,
            code=code,
            phone_code_hash=phone_code_hash,
            password=password,
        )
        return TelegramAuthSignInResponse(**payload)

    async def start_outbound_call(self, payload: OutboundCallRequest) -> OutboundCallResponse:
        result = await self.telegram.start_outbound_call(
            target_user=payload.target_user,
            purpose=payload.purpose.value,
            initial_audio_path=payload.initial_audio_path,
            metadata=payload.metadata,
        )
        return OutboundCallResponse(**result)

    async def append_transcript(self, call_id: str, payload: CallTranscriptRequest) -> InboundCallResponse:
        self.telegram.append_transcript(call_id, payload.transcript, metadata=payload.metadata)
        return InboundCallResponse(
            call_id=call_id,
            status="received",
            detail="Transcript accepted and stored.",
        )

    async def finalize_call(self, payload: PostCallEventRequest) -> PostCallSummary:
        self.telegram.append_transcript(payload.call_id, payload.transcript, metadata=payload.metadata)
        call = self.telegram.get_call(payload.call_id) or {}
        call["status"] = "completed"
        return PostCallSummary(
            call_id=payload.call_id,
            status="completed",
            detail="Post-call event stored.",
        )

    async def generate_agent_reply(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any],
    ) -> AgentReplyResponse:
        self.telegram.append_transcript(call_id, transcript, metadata=context)

        if not self.settings.zai_api_key:
            fallback = "I captured this message and will follow up shortly."
            return AgentReplyResponse(call_id=call_id, reply=fallback, action_items=[])

        system = (
            "You are an AI secretary. Return JSON with keys `reply` and `action_items` only. "
            "`reply` should be a short phone-friendly response. "
            "`action_items` should be a list of concise next actions."
        )
        payload = {
            "model": self.settings.zai_model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps({"call_id": call_id, "transcript": transcript, "context": context}),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }
        result = await self._zai_chat_completion(payload)
        if result.get("error"):
            fallback = "Thanks, I noted that and will send this to the team."
            return AgentReplyResponse(call_id=call_id, reply=fallback, action_items=[])

        message = self._extract_message(result["data"])
        raw = (message.get("content") or "").strip()
        parsed = self._try_parse_json(raw)
        reply = str(parsed.get("reply") or raw or "Acknowledged.")
        actions = parsed.get("action_items")
        action_items = [str(item) for item in actions] if isinstance(actions, list) else []

        call = self.telegram.get_call(call_id)
        if call is not None:
            call["last_agent_reply"] = reply
            call["last_action_items"] = action_items

        return AgentReplyResponse(call_id=call_id, reply=reply, action_items=action_items)

    async def get_call(self, call_id: str) -> dict[str, Any] | None:
        return self.telegram.get_call(call_id)

    async def list_calls(self) -> list[dict[str, Any]]:
        return self.telegram.list_calls()

    async def list_call_events(self, limit: int) -> list[dict[str, Any]]:
        return self.telegram.list_events(limit=limit)

    async def end_call(self, call_id: str) -> CallEventAck:
        result = await self.telegram.end_call(call_id)
        return CallEventAck(**result)

    async def stream_audio_out(self, call_id: str, payload: CallAudioPlayRequest) -> CallAudioResponse:
        result = await self.telegram.stream_audio_out(call_id, payload.audio_path)
        return CallAudioResponse(**result)

    async def stream_audio_in(self, call_id: str, payload: CallAudioRecordRequest) -> CallAudioResponse:
        result = await self.telegram.stream_audio_in(call_id, payload.output_path)
        return CallAudioResponse(**result)

    async def _zai_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.zai_api_key:
            return {"error": "Missing ZAI_API_KEY in environment."}

        base_url = self.settings.zai_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.zai_api_key}",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.zai_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 300:
                return {
                    "error": f"GLM request failed ({response.status_code}).",
                    "raw": response.text[:240],
                }
            return {"data": response.json()}
        except Exception as exc:
            return {"error": f"Connection error: {exc.__class__.__name__}"}

    @staticmethod
    def _extract_message(data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices") or []
        if not choices:
            return {}
        msg = choices[0].get("message") or {}
        if not isinstance(msg, dict):
            return {}
        return msg

    @staticmethod
    def _try_parse_json(raw: str) -> dict[str, Any]:
        if not raw:
            return {}
        trimmed = raw.strip()
        if trimmed.startswith("```"):
            trimmed = trimmed.strip("`")
            if trimmed.startswith("json"):
                trimmed = trimmed[4:].strip()
        try:
            data = json.loads(trimmed)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
