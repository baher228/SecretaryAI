import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings


_DEFAULT_TEMPLATES = [
    {
        "id": "greeting",
        "keywords": ["hello", "hi", "hey", "good morning", "good evening"],
        "reply": "Hi. I’m here. Tell me what you need.",
        "priority": 1,
    },
    {
        "id": "repeat",
        "keywords": ["repeat", "say again", "again", "what did you say"],
        "reply": "Sure. I can repeat that. What part should I repeat?",
        "priority": 2,
    },
    {
        "id": "clarify",
        "keywords": ["you there", "can you hear me", "hello are you there"],
        "reply": "Yes, I can hear you. Please go ahead.",
        "priority": 3,
    },
    {
        "id": "slow_down",
        "keywords": ["slow down", "too fast", "speak slower"],
        "reply": "Understood. I will speak slower.",
        "priority": 4,
    },
    {
        "id": "volume_issue",
        "keywords": ["cant hear", "can't hear", "too quiet", "volume"],
        "reply": "Understood. I will keep replies short and clear.",
        "priority": 4,
    },
    {
        "id": "availability_check",
        "keywords": ["am i free", "availability", "free tomorrow", "free at"],
        "reply": "Let me quickly check your availability.",
        "calendar_check": True,
        "priority": 10,
    },
    {
        "id": "reminder_set",
        "keywords": ["set a reminder", "remind me", "set reminder", "reminder"],
        "reply": "Absolutely. Let me check your availability and queue this reminder.",
        "calendar_check": True,
        "calendar_enqueue": True,
        "priority": 11,
    },
    {
        "id": "meeting_schedule",
        "keywords": ["schedule meeting", "book meeting", "add meeting", "create event"],
        "reply": "Absolutely. I’ll check your timetable and queue this for scheduling.",
        "calendar_check": True,
        "calendar_enqueue": True,
        "priority": 11,
    },
    {
        "id": "calendar_today",
        "keywords": ["calendar", "today", "schedule", "upcoming"],
        "reply": "I can check your upcoming schedule now.",
        "calendar_check": True,
        "priority": 8,
    },
    {
        "id": "calendar_delete",
        "keywords": ["delete event", "remove event", "cancel event"],
        "reply": "Okay. I can remove that event after you confirm which one.",
        "calendar_enqueue": True,
        "priority": 9,
    },
    {
        "id": "time_query",
        "keywords": ["what time", "when is", "next meeting"],
        "reply": "I can check that now. Give me one second.",
        "calendar_check": True,
        "priority": 7,
    },
    {
        "id": "reschedule",
        "keywords": ["reschedule", "move meeting", "another time"],
        "reply": "Understood. I can help reschedule it.",
        "calendar_enqueue": True,
        "priority": 9,
    },
    {
        "id": "confirm",
        "keywords": ["yes", "confirm", "correct", "go ahead"],
        "reply": "Great. Confirmed.",
        "priority": 1,
    },
    {
        "id": "reject",
        "keywords": ["no", "not that", "wrong", "cancel that"],
        "reply": "Okay. I won’t do that. Tell me the correct option.",
        "priority": 1,
    },
    {
        "id": "thanks",
        "keywords": ["thanks", "thank you", "appreciate"],
        "reply": "You’re welcome.",
        "priority": 1,
    },
    {
        "id": "hold_on",
        "keywords": ["wait", "hold on", "one second"],
        "reply": "Sure, I’ll wait.",
        "priority": 1,
    },
    {
        "id": "goodbye",
        "keywords": ["bye", "goodbye", "hang up", "that is all"],
        "reply": "Got it. I’ll wrap up now.",
        "priority": 2,
    },
]


class LiveTemplateMatcher:
    """Fast keyword template router for call-mode replies before LLM."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(self.settings.agent_live_template_path)
        self.templates = self._load_templates()

    def match(self, transcript: str) -> dict[str, Any] | None:
        if not self.settings.agent_live_template_enabled:
            return None
        text = " ".join((transcript or "").split()).strip().lower()
        if not text:
            return None

        best_item: dict[str, Any] | None = None
        best_score = 0
        best_priority = -1
        words = [w for w in text.split() if w]

        for item in self.templates:
            keywords = [str(k).strip().lower() for k in item.get("keywords", []) if str(k).strip()]
            if not keywords:
                continue
            score = 0
            for kw in keywords:
                if kw in text:
                    score += 2
                    continue

                # Fuzzy single-token match only when similarity is high enough.
                kw_parts = [p for p in kw.split() if p]
                if len(kw_parts) == 1 and len(kw_parts[0]) >= 4:
                    token = kw_parts[0]
                    best_ratio = 0.0
                    for w in words:
                        if abs(len(w) - len(token)) > 2:
                            continue
                        ratio = SequenceMatcher(None, token, w).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                    if best_ratio >= 0.82:
                        score += 1
            if score <= 0:
                continue
            priority = int(item.get("priority", 0))
            if score > best_score or (score == best_score and priority > best_priority):
                best_item = item
                best_score = score
                best_priority = priority

        if best_item is None:
            return None

        reply = str(best_item.get("reply") or "").strip()
        if not reply:
            return None

        return {
            "id": str(best_item.get("id") or "template"),
            "reply": reply,
            "score": best_score,
            "priority": best_priority,
            "calendar_check": bool(best_item.get("calendar_check", False)),
            "calendar_enqueue": bool(best_item.get("calendar_enqueue", False)),
        }

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
