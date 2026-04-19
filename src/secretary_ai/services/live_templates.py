import json
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings


_DEFAULT_TEMPLATES = [
    {
        "id": "greeting",
        "keywords": ["hello", "hi", "hey"],
        "reply": "Hi. I’m here. Tell me what you need.",
    },
    {
        "id": "repeat",
        "keywords": ["repeat", "say again", "again"],
        "reply": "Sure. I can repeat that. What part should I repeat?",
    },
    {
        "id": "calendar_today",
        "keywords": ["calendar", "today", "schedule"],
        "reply": "I can check your upcoming schedule now.",
    },
    {
        "id": "goodbye",
        "keywords": ["bye", "goodbye", "hang up"],
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
                    return valid
        except Exception:
            pass
        return list(_DEFAULT_TEMPLATES)
