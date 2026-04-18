import json
from typing import Any

import httpx

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import AgentAnalyzeResponse, IntentType


class SecretaryAIAgent:
    """LLM-driven secretary brain with structured intent/action extraction."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.histories: dict[str, list[dict[str, str]]] = {}

    async def analyze_turn(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any] | None = None,
    ) -> AgentAnalyzeResponse:
        context = context or {}
        history = self.histories.setdefault(call_id, [])
        history.append({"role": "caller", "content": transcript})

        if not self.settings.zai_api_key:
            return self._heuristic_response(call_id, transcript, context)

        messages = self._build_messages(call_id, transcript, context, history)
        payload = {
            "model": self.settings.zai_model,
            "messages": messages,
            "temperature": 0.15,
            "max_tokens": 450,
        }
        result = await self._zai_chat_completion(payload)
        if result.get("error"):
            return self._heuristic_response(call_id, transcript, context)

        message = self._extract_message(result["data"])
        raw_model_text = str(message.get("content") or "").strip()
        if not raw_model_text:
            raw_model_text = str(message.get("reasoning_content") or "").strip()
        parsed = self._try_parse_json(raw_model_text)
        if not parsed:
            return self._heuristic_response(call_id, transcript, context)

        response = self._normalize_response(call_id=call_id, parsed=parsed)
        history.append({"role": "assistant", "content": response.reply})
        return response

    def _build_messages(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any],
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        system = (
            "You are a highly reliable AI secretary for phone calls. "
            "Return ONLY valid JSON with this schema: "
            "{"
            "\"intent\": \"book_event|reschedule_event|cancel_event|reminder|confirmation|follow_up|"
            "transfer_human|leave_message|general_query|unknown\", "
            "\"confidence\": number between 0 and 1, "
            "\"reply\": short voice-ready response sentence, "
            "\"requires_human\": boolean, "
            "\"transfer_reason\": string or null, "
            "\"action_items\": array of strings, "
            "\"extracted_fields\": object with useful slots like date/time/name/phone/topic"
            "}. "
            "Output must be a single JSON object only, no markdown, no code fences, no extra text. "
            "Be concise and practical. If unsure, use intent=unknown with lower confidence."
        )
        compact_history = history[-6:]
        history_text = "\n".join(
            f"{turn.get('role', 'unknown')}: {turn.get('content', '')}" for turn in compact_history
        )
        user_payload = {
            "call_id": call_id,
            "latest_transcript": transcript,
            "context": context,
            "recent_history": history_text,
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload)},
        ]

    def _normalize_response(
        self,
        call_id: str,
        parsed: dict[str, Any],
    ) -> AgentAnalyzeResponse:
        raw_intent = str(parsed.get("intent") or IntentType.UNKNOWN.value).lower().strip()
        valid_intents = {item.value for item in IntentType}
        if raw_intent not in valid_intents:
            raw_intent = IntentType.UNKNOWN.value

        reply = str(parsed.get("reply") or "").strip()
        if not reply:
            reply = self._fallback_reply_from_intent(raw_intent)

        raw_confidence = parsed.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        action_items_raw = parsed.get("action_items")
        if isinstance(action_items_raw, list):
            action_items = [str(item).strip() for item in action_items_raw if str(item).strip()]
        else:
            action_items = []

        requires_human = bool(parsed.get("requires_human", False)) or (
            raw_intent == IntentType.TRANSFER_HUMAN.value
        )
        transfer_reason = parsed.get("transfer_reason")
        transfer_reason_str = str(transfer_reason).strip() if transfer_reason is not None else None
        if transfer_reason_str == "":
            transfer_reason_str = None
        if requires_human and not transfer_reason_str:
            transfer_reason_str = "Caller requested a person."

        extracted_fields = parsed.get("extracted_fields")
        if not isinstance(extracted_fields, dict):
            extracted_fields = {}

        return AgentAnalyzeResponse(
            call_id=call_id,
            intent=IntentType(raw_intent),
            confidence=confidence,
            reply=reply,
            requires_human=requires_human,
            transfer_reason=transfer_reason_str,
            action_items=action_items[:8],
            extracted_fields=extracted_fields,
            model=self.settings.zai_model,
        )

    def _heuristic_response(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any] | None,
    ) -> AgentAnalyzeResponse:
        text = transcript.lower()
        intent = IntentType.GENERAL_QUERY
        action_items: list[str] = []
        extracted: dict[str, Any] = {}

        if any(token in text for token in ["reschedule", "move meeting", "another time"]):
            intent = IntentType.RESCHEDULE_EVENT
            action_items.append("Check available slots and propose alternatives.")
        elif any(token in text for token in ["book", "schedule", "set up meeting", "appointment"]):
            intent = IntentType.BOOK_EVENT
            action_items.append("Create a draft calendar event from caller details.")
        elif any(token in text for token in ["cancel", "call it off"]):
            intent = IntentType.CANCEL_EVENT
            action_items.append("Locate matching event and cancel after confirmation.")
        elif any(token in text for token in ["human", "agent", "person"]):
            intent = IntentType.TRANSFER_HUMAN
            action_items.append("Escalate to human teammate.")
        elif any(token in text for token in ["remind", "reminder"]):
            intent = IntentType.REMINDER
            action_items.append("Create reminder task in follow-up queue.")

        if context:
            extracted["context_keys"] = sorted(context.keys())

        return AgentAnalyzeResponse(
            call_id=call_id,
            intent=intent,
            confidence=0.45,
            reply=self._fallback_reply_from_intent(intent.value),
            requires_human=intent == IntentType.TRANSFER_HUMAN,
            transfer_reason="Caller asked for a human." if intent == IntentType.TRANSFER_HUMAN else None,
            action_items=action_items,
            extracted_fields=extracted,
            model=self.settings.zai_model,
        )

    @staticmethod
    def _fallback_reply_from_intent(intent: str) -> str:
        if intent == IntentType.BOOK_EVENT.value:
            return "Got it. I can help book that, please share the best date and time."
        if intent == IntentType.RESCHEDULE_EVENT.value:
            return "Understood. I can reschedule this, please confirm your preferred new time."
        if intent == IntentType.CANCEL_EVENT.value:
            return "Understood. I can cancel that after one quick confirmation."
        if intent == IntentType.TRANSFER_HUMAN.value:
            return "I will connect you with a human teammate now."
        return "Thanks, I captured that and will proceed with the next step."

    async def _zai_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            pass

        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start >= 0 and end > start:
            candidate = trimmed[start : end + 1]
            try:
                data = json.loads(candidate)
                return data if isinstance(data, dict) else {}
            except Exception:
                pass

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(trimmed):
            if ch != "{":
                continue
            try:
                data, _ = decoder.raw_decode(trimmed[idx:])
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
        return {}
