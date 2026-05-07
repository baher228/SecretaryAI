import json
from typing import Any

from secretary_ai.core.config import Settings
from secretary_ai.core.locales import (
    AI_AGENT_LIVE_SUFFIX,
    AI_AGENT_SYSTEM_PROMPT,
    FALLBACK_DEFAULT,
    FALLBACK_REPLIES,
    TRANSFER_REASON_DEFAULT,
    t,
    t_dict,
)
from secretary_ai.domain.models import AgentAnalyzeResponse, IntentType
from secretary_ai.services.openai_client import extract_message, openai_chat_completion

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
        if not self.settings.openai_api_key:
            return self._heuristic_response(call_id, transcript, context)

        payload = {
            "model": self.settings.openai_model,
            "messages": self._build_messages(
                call_id=call_id,
                transcript=transcript,
                context=context,
                history=history,
                history_turns=history_turns,
                live_mode=live_mode,
            ),
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        result = await openai_chat_completion(self.settings, payload)
        if result.get("error"):
            return self._heuristic_response(call_id, transcript, context)

        message = extract_message(result["data"])
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
        lang = self.settings.language
        system = t(AI_AGENT_SYSTEM_PROMPT, lang)
        if live_mode:
            system += t(AI_AGENT_LIVE_SUFFIX, lang)
        compact_history = history[-max(0, int(history_turns)) :] if history_turns > 0 else []
        history_text = "\n".join(f"{h.get('role', 'unknown')}: {h.get('content', '')}" for h in compact_history)
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

        lang = self.settings.language
        reply = str(parsed.get("reply") or "").strip() or self._fallback_reply_from_intent(raw_intent, lang)
        confidence = self._normalized_confidence(parsed.get("confidence", 0.0))

        action_items_raw = parsed.get("action_items")
        action_items = (
            [str(item).strip() for item in action_items_raw if str(item).strip()]
            if isinstance(action_items_raw, list)
            else []
        )

        requires_human = bool(parsed.get("requires_human", False)) or raw_intent == IntentType.TRANSFER_HUMAN.value
        transfer_reason = self._normalized_transfer_reason(parsed.get("transfer_reason"), requires_human, self.settings.language)
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
            model=self.settings.openai_model,
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
            reply=self._fallback_reply_from_intent(intent.value, self.settings.language),
            requires_human=intent == IntentType.TRANSFER_HUMAN,
            transfer_reason=t(TRANSFER_REASON_DEFAULT, self.settings.language) if intent == IntentType.TRANSFER_HUMAN else None,
            action_items=action_items,
            extracted_fields=extracted,
            model=self.settings.openai_model,
        )

    @staticmethod
    def _fallback_reply_from_intent(intent: str, lang: str = "en") -> str:
        return t_dict(FALLBACK_REPLIES, lang).get(intent, t(FALLBACK_DEFAULT, lang))

    @staticmethod
    def _normalized_confidence(raw_confidence: Any) -> float:
        try:
            return max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalized_transfer_reason(transfer_reason: Any, requires_human: bool, lang: str = "en") -> str | None:
        reason = str(transfer_reason).strip() if transfer_reason is not None else None
        if reason == "":
            reason = None
        if requires_human and not reason:
            reason = t(TRANSFER_REASON_DEFAULT, lang)
        return reason



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
