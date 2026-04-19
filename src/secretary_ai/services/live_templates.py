import json
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings


_DEFAULT_TEMPLATES = [
    {
        "id": "greeting",
        "keywords": ["hello", "hi", "hey", "good morning", "good evening"],
        "reply": "Hi. I’m here. Tell me what you need.",
    },
    {
        "id": "repeat",
        "keywords": ["repeat", "say again", "again", "what did you say"],
        "reply": "Sure. I can repeat that. What part should I repeat?",
    },
    {
        "id": "clarify",
        "keywords": ["you there", "can you hear me", "hello are you there"],
        "reply": "Yes, I can hear you. Please go ahead.",
    },
    {
        "id": "slow_down",
        "keywords": ["slow down", "too fast", "speak slower"],
        "reply": "Understood. I will speak slower.",
    },
    {
        "id": "volume_issue",
        "keywords": ["cant hear", "can't hear", "too quiet", "volume"],
        "reply": "Understood. I will keep replies short and clear.",
    },
    {
        "id": "calendar_today",
        "keywords": ["calendar", "today", "schedule", "upcoming"],
        "reply": "I can check your upcoming schedule now.",
    },
    {
        "id": "calendar_add",
        "keywords": ["add to calendar", "create event", "schedule meeting", "book meeting"],
        "reply": "Got it. I can add that to your calendar. Please confirm time.",
    },
    {
        "id": "calendar_delete",
        "keywords": ["delete event", "remove event", "cancel event"],
        "reply": "Okay. I can remove that event after you confirm which one.",
    },
    {
        "id": "time_query",
        "keywords": ["what time", "when is", "next meeting"],
        "reply": "I can check that now. Give me one second.",
    },
    {
        "id": "reminder",
        "keywords": ["remind me", "set reminder", "reminder"],
        "reply": "Sure. I can set that reminder for you.",
    },
    {
        "id": "reschedule",
        "keywords": ["reschedule", "move meeting", "another time"],
        "reply": "Understood. I can help reschedule it.",
    },
    {
        "id": "confirm",
        "keywords": ["yes", "confirm", "correct", "go ahead"],
        "reply": "Great. Confirmed.",
    },
    {
        "id": "reject",
        "keywords": ["no", "not that", "wrong", "cancel that"],
        "reply": "Okay. I won’t do that. Tell me the correct option.",
    },
    {
        "id": "thanks",
        "keywords": ["thanks", "thank you", "appreciate"],
        "reply": "You’re welcome.",
    },
    {
        "id": "hold_on",
        "keywords": ["wait", "hold on", "one second"],
        "reply": "Sure, I’ll wait.",
    },
    {
        "id": "goodbye",
        "keywords": ["bye", "goodbye", "hang up", "that is all"],
        "reply": "Got it. I’ll wrap up now.",
    },
]


class LiveTemplateMatcher:
    """Fast keyword template router for call-mode replies before LLM."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(self.settings.agent_live_template_path)
        self.templates = self._load_templates()

    def match(self, transcript: str) -> str | None:
        if not self.settings.agent_live_template_enabled:
            return None
        text = " ".join((transcript or "").split()).strip().lower()
        if not text:
            return None

        best_reply: str | None = None
        best_score = 0
        for item in self.templates:
            keywords = [str(k).strip().lower() for k in item.get("keywords", []) if str(k).strip()]
            if not keywords:
                continue
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_reply = str(item.get("reply") or "").strip() or None

        return best_reply if best_score > 0 else None

    def _load_templates(self) -> list[dict[str, Any]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps(_DEFAULT_TEMPLATES, ensure_ascii=False, indent=2), encoding="utf-8")
            return list(_DEFAULT_TEMPLATES)

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                valid = [item for item in raw if isinstance(item, dict)]
                if valid:
                    merged = self._merge_with_defaults(valid)
                    self.path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
                    return merged
        except Exception:
            pass
        return list(_DEFAULT_TEMPLATES)

    @staticmethod
    def _merge_with_defaults(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for item in existing:
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                continue
            by_id[item_id] = item

        merged: list[dict[str, Any]] = []
        for default in _DEFAULT_TEMPLATES:
            default_id = str(default.get("id"))
            merged.append(by_id.get(default_id, default))

        for item_id, item in by_id.items():
            if all(str(d.get("id")) != item_id for d in _DEFAULT_TEMPLATES):
                merged.append(item)
        return merged
