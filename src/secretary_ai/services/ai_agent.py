import json
from typing import Any

import httpx

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import AgentAnalyzeResponse, IntentType


_FALLBACK_REPLIES = {
    IntentType.BOOK_EVENT.value: "Got it. I can help book that, please share the best date and time.",
    IntentType.RESCHEDULE_EVENT.value: "Understood. I can reschedule this, please confirm your preferred new time.",
    IntentType.CANCEL_EVENT.value: "Understood. I can cancel that after one quick confirmation.",
    IntentType.TRANSFER_HUMAN.value: "I will connect you with a human teammate now.",
    IntentType.PLAN_ROUTE.value: "I will calculate the fastest route for you right away.",
    IntentType.SEARCH_BOOKING.value: "Searching for availability now, one moment.",
}

_HEURISTIC_RULES: list[tuple[IntentType, tuple[str, ...], str]] = [
    (IntentType.RESCHEDULE_EVENT, ("reschedule", "move meeting", "another time"), "Check available slots and propose alternatives."),
    (IntentType.BOOK_EVENT, ("book", "schedule", "set up meeting", "appointment"), "Create a draft calendar event from caller details."),
    (IntentType.CANCEL_EVENT, ("cancel", "call it off"), "Locate matching event and cancel after confirmation."),
    (IntentType.TRANSFER_HUMAN, ("human", "agent", "person"), "Escalate to human teammate."),
    (IntentType.REMINDER, ("remind", "reminder"), "Create reminder task in follow-up queue."),
    (IntentType.PLAN_ROUTE, ("route", "directions", "drive to", "navigate"), "Plan route and provide estimated time."),
    (IntentType.SEARCH_BOOKING, ("find a restaurant", "hotel", "flight", "tickets"), "Search online for booking options."),
]


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
        return await self._analyze_with_profile(
            call_id=call_id,
            transcript=transcript,
            context=context,
            history=history,
            max_tokens=self.settings.agent_max_tokens,
            history_turns=self.settings.agent_history_turns,
            temperature=0.15,
            live_mode=False,
        )

    async def analyze_turn_live(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any] | None = None,
    ) -> AgentAnalyzeResponse:
        context = context or {}
        history = self.histories.setdefault(call_id, [])
        history.append({"role": "caller", "content": transcript})
        return await self._analyze_with_profile(
            call_id=call_id,
            transcript=transcript,
            context=context,
            history=history,
            max_tokens=max(32, int(self.settings.agent_live_max_tokens)),
            history_turns=max(0, int(self.settings.agent_live_history_turns)),
            temperature=float(self.settings.agent_live_temperature),
            live_mode=True,
        )

    async def _analyze_with_profile(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any],
        history: list[dict[str, str]],
        max_tokens: int,
        history_turns: int,
        temperature: float,
        live_mode: bool,
    ) -> AgentAnalyzeResponse:
        if not self.settings.zai_api_key:
            return self._heuristic_response(call_id, transcript, context)

        payload = {
            "model": self.settings.zai_model,
            "messages": self._build_messages(
                call_id=call_id,
                transcript=transcript,
                context=context,
                history=history,
                history_turns=history_turns,
                live_mode=live_mode,
            ),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        result = await self._zai_chat_completion(payload)
        if result.get("error"):
            return self._heuristic_response(call_id, transcript, context)

        message = self._extract_message(result["data"])
        raw_model_text = str(message.get("content") or message.get("reasoning_content") or "").strip()
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
        history_turns: int,
        live_mode: bool,
    ) -> list[dict[str, str]]:
        system = (
            "You are a highly reliable AI secretary for phone calls. "
            "Return ONLY valid JSON with this schema: "
            "{"
            '"intent": "book_event|reschedule_event|cancel_event|reminder|confirmation|follow_up|'
            'transfer_human|leave_message|general_query|plan_route|search_booking|unknown", '
            '"confidence": number between 0 and 1, '
            '"reply": short voice-ready response sentence, '
            '"requires_human": boolean, '
            '"transfer_reason": string or null, '
            '"action_items": array of strings, '
            '"extracted_fields": object with useful slots like date/time/name/phone/topic'
            "}. "
            "Output must be a single JSON object only, no markdown, no code fences, no extra text. "
            "Be concise and practical. Keep reply under 18 words. "
            "If unsure, use intent=unknown with lower confidence."
        )
        if live_mode:
            system += " Live-call mode: prioritize immediate short reply and minimal planning overhead."
        compact_history = history[-max(0, int(history_turns)) :] if history_turns > 0 else []
        history_text = "\n".join(f"{t.get('role', 'unknown')}: {t.get('content', '')}" for t in compact_history)
        return [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "call_id": call_id,
                        "latest_transcript": transcript,
                        "context": context,
                        "recent_history": history_text,
                    }
                ),
            },
        ]

    def _normalize_response(self, call_id: str, parsed: dict[str, Any]) -> AgentAnalyzeResponse:
        raw_intent = str(parsed.get("intent") or IntentType.UNKNOWN.value).lower().strip()
        if raw_intent not in {i.value for i in IntentType}:
            raw_intent = IntentType.UNKNOWN.value

        reply = str(parsed.get("reply") or "").strip() or self._fallback_reply_from_intent(raw_intent)
        confidence = self._normalized_confidence(parsed.get("confidence", 0.0))

        action_items_raw = parsed.get("action_items")
        action_items = (
            [str(item).strip() for item in action_items_raw if str(item).strip()]
            if isinstance(action_items_raw, list)
            else []
        )

        requires_human = bool(parsed.get("requires_human", False)) or raw_intent == IntentType.TRANSFER_HUMAN.value
        transfer_reason = self._normalized_transfer_reason(parsed.get("transfer_reason"), requires_human)
        extracted_fields = parsed.get("extracted_fields") if isinstance(parsed.get("extracted_fields"), dict) else {}

        return AgentAnalyzeResponse(
            call_id=call_id,
            intent=IntentType(raw_intent),
            confidence=confidence,
            reply=reply,
            requires_human=requires_human,
            transfer_reason=transfer_reason,
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

        for rule_intent, tokens, action in _HEURISTIC_RULES:
            if any(token in text for token in tokens):
                intent = rule_intent
                action_items = [action]
                break

        extracted: dict[str, Any] = {}
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
        return _FALLBACK_REPLIES.get(intent, "Thanks, I captured that and will proceed with the next step.")

    @staticmethod
    def _normalized_confidence(raw_confidence: Any) -> float:
        try:
            return max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalized_transfer_reason(transfer_reason: Any, requires_human: bool) -> str | None:
        reason = str(transfer_reason).strip() if transfer_reason is not None else None
        if reason == "":
            reason = None
        if requires_human and not reason:
            reason = "Caller requested a person."
        return reason

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
                return {"error": f"GLM request failed ({response.status_code}).", "raw": response.text[:240]}
            return {"data": response.json()}
        except Exception as exc:
            return {"error": f"Connection error: {exc.__class__.__name__}"}

    @staticmethod
    def _extract_message(data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices") or []
        if not choices:
            return {}
        msg = choices[0].get("message") or {}
        return msg if isinstance(msg, dict) else {}

    @staticmethod
    def _try_parse_json(raw: str) -> dict[str, Any]:
        if not raw:
            return {}

        trimmed = raw.strip()
        if trimmed.startswith("```"):
            trimmed = trimmed.strip("`")
            if trimmed.startswith("json"):
                trimmed = trimmed[4:].strip()

        def try_load(candidate: str) -> dict[str, Any]:
            try:
                parsed = json.loads(candidate)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

        direct = try_load(trimmed)
        if direct:
            return direct

        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start >= 0 and end > start:
            embedded = try_load(trimmed[start : end + 1])
            if embedded:
                return embedded

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(trimmed):
            if ch != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(trimmed[idx:])
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return {}
