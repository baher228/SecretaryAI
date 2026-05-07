"""Wake-word engine for routing voice commands to specific action handlers.

Listens for configurable trigger phrases (e.g. "Secretary, schedule…") in
live-call transcripts and routes to the appropriate action pipeline —
scheduling, booking search, reminder, directions, etc.  The engine strips
the wake-word prefix and returns the action type + remaining payload text.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in action definitions
# ---------------------------------------------------------------------------

BUILTIN_ACTIONS: list[dict[str, Any]] = [
    {
        "action": "schedule",
        "phrases": [
            "schedule",
            "set up a meeting",
            "book a meeting",
            "create an event",
            "add to calendar",
        ],
        "description": "Route to calendar scheduling flow.",
    },
    {
        "action": "remind",
        "phrases": [
            "remind me",
            "set a reminder",
            "reminder for",
            "don't let me forget",
        ],
        "description": "Route to reminder creation flow.",
    },
    {
        "action": "find_restaurant",
        "phrases": [
            "find a restaurant",
            "find me a restaurant",
            "search for restaurants",
            "restaurant near",
            "where to eat",
            "good place to eat",
            "dinner reservations",
            "lunch spot",
            "book a table",
            "book a restaurant",
        ],
        "description": "Route to restaurant booking search.",
    },
    {
        "action": "find_hotel",
        "phrases": [
            "find a hotel",
            "find me a hotel",
            "search for hotels",
            "hotel near",
            "place to stay",
            "book a hotel",
            "accommodation",
            "hotel booking",
        ],
        "description": "Route to hotel booking search.",
    },
    {
        "action": "find_event",
        "phrases": [
            "find an event",
            "find tickets",
            "search for events",
            "concerts near",
            "things to do",
            "what's happening",
            "theatre tickets",
            "buy tickets",
        ],
        "description": "Route to event/ticket search.",
    },
    {
        "action": "find_travel",
        "phrases": [
            "find a flight",
            "search for flights",
            "book a flight",
            "train to",
            "bus to",
            "travel to",
            "flight to",
            "how to get to",
        ],
        "description": "Route to travel/transport search.",
    },
    {
        "action": "plan_evening",
        "phrases": [
            "plan an evening",
            "plan tonight",
            "evening out",
            "plan a night out",
            "dinner and show",
            "dinner and entertainment",
        ],
        "description": "Route to evening planning (dinner + entertainment).",
    },
    {
        "action": "directions",
        "phrases": [
            "directions to",
            "navigate to",
            "route to",
            "how do i get to",
            "drive to",
            "walk to",
        ],
        "description": "Route to map/directions flow.",
    },
    {
        "action": "remember",
        "phrases": [
            "remember that",
            "remember my",
            "note that",
            "write down",
            "save this",
        ],
        "description": "Route to memory store for saving facts.",
    },
]


class WakeWordMatch:
    """Result of a successful wake-word detection."""

    __slots__ = ("action", "payload", "wake_phrase", "confidence")

    def __init__(self, action: str, payload: str, wake_phrase: str, confidence: float) -> None:
        self.action = action
        self.payload = payload
        self.wake_phrase = wake_phrase
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "payload": self.payload,
            "wake_phrase": self.wake_phrase,
            "confidence": self.confidence,
        }


class WakeWordEngine:
    """Detects wake words/phrases in transcripts and routes to actions.

    Supports:
    - Optional wake-word prefix (e.g. "Secretary, …")
    - Action-specific trigger phrases
    - Custom user-defined wake-word rules from a JSON config file
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._wake_prefix = self._normalize(settings.wake_word_prefix)
        self._wake_aliases = [
            self._normalize(a)
            for a in (settings.wake_word_aliases.split(",") if settings.wake_word_aliases else [])
            if a.strip()
        ]
        self._actions = self._load_actions()
        logger.info(
            "WakeWordEngine initialised: prefix=%r, aliases=%d, actions=%d",
            self._wake_prefix,
            len(self._wake_aliases),
            len(self._actions),
        )

    def detect(self, transcript: str) -> WakeWordMatch | None:
        """Check transcript for wake-word + action phrase.

        Returns a ``WakeWordMatch`` if detected, else ``None``.
        """
        if not self.settings.wake_word_enabled:
            return None

        text = self._normalize(transcript)
        if not text:
            return None

        # Strip wake-word prefix if present.
        stripped = self._strip_prefix(text)
        has_prefix = stripped != text

        # If wake_word_require_prefix is True, only match when prefix is present.
        if self.settings.wake_word_require_prefix and not has_prefix:
            return None

        # Find best action match.
        best: WakeWordMatch | None = None
        best_len = 0

        for action_def in self._actions:
            action = action_def["action"]
            for phrase in action_def["phrases"]:
                norm_phrase = self._normalize(phrase)
                if not norm_phrase:
                    continue
                pattern = r"\b" + re.escape(norm_phrase) + r"\b"
                m = re.search(pattern, stripped)
                if m:
                    phrase_len = len(norm_phrase)
                    if phrase_len > best_len:
                        # Extract payload: everything after the matched phrase
                        payload = stripped[m.end():].strip().strip(".,!?")
                        confidence = 0.9 if has_prefix else 0.7
                        best = WakeWordMatch(
                            action=action,
                            payload=payload,
                            wake_phrase=phrase,
                            confidence=confidence,
                        )
                        best_len = phrase_len

        return best

    def list_actions(self) -> list[dict[str, Any]]:
        """Return all registered action definitions."""
        return [
            {"action": a["action"], "phrases": a["phrases"], "description": a.get("description", "")}
            for a in self._actions
        ]

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase, collapse whitespace, strip punctuation."""
        t = re.sub(r"[^\w\s]", " ", (text or "").lower())
        return " ".join(t.split()).strip()

    def _strip_prefix(self, text: str) -> str:
        """Remove the wake-word prefix (or any alias) from the beginning."""
        for prefix in [self._wake_prefix] + self._wake_aliases:
            if not prefix:
                continue
            if text.startswith(prefix):
                remainder = text[len(prefix):].strip()
                if remainder:
                    return remainder
        return text

    def _load_actions(self) -> list[dict[str, Any]]:
        """Load built-in actions plus optional user-defined overrides."""
        actions = list(BUILTIN_ACTIONS)

        custom_path = Path(self.settings.wake_word_config_path)
        if custom_path.is_file():
            try:
                data = json.loads(custom_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("action") and item.get("phrases"):
                            actions.append(item)
                    logger.info("Loaded %d custom wake-word actions from %s", len(data), custom_path)
            except Exception:
                logger.warning("Failed to load custom wake-word config from %s", custom_path, exc_info=True)

        return actions
