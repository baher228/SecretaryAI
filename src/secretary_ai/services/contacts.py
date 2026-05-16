"""Simple JSON-backed contact book for caller preferences and names."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings

logger = logging.getLogger(__name__)


class ContactBook:
    """Persistent contact store with caller names, language, and preferences."""

    def __init__(self, settings: Settings) -> None:
        self._path = Path(settings.telegram_audio_root).parent / "cache" / "contacts.json"
        self._contacts: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
        except Exception:
            logger.warning("Failed to load contacts from %s", self._path, exc_info=True)
        return {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._contacts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Failed to save contacts to %s", self._path, exc_info=True)

    def get(self, caller_id: str) -> dict[str, Any] | None:
        """Return contact record for a caller, or None if unknown."""
        return self._contacts.get(caller_id)

    def upsert(self, caller_id: str, **fields: Any) -> dict[str, Any]:
        """Create or update a contact. Returns the updated record."""
        existing = self._contacts.get(caller_id, {})
        existing.update({k: v for k, v in fields.items() if v is not None})
        existing["caller_id"] = caller_id
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "created_at" not in existing:
            existing["created_at"] = existing["updated_at"]
        self._contacts[caller_id] = existing
        self._save()
        return existing

    def record_call(self, caller_id: str) -> None:
        """Increment the call count and update last_called timestamp."""
        contact = self._contacts.get(caller_id, {})
        call_count = contact.get("call_count", 0) + 1
        last_called = datetime.now(timezone.utc).isoformat()
        self.upsert(caller_id, call_count=call_count, last_called=last_called)

    def list_all(self) -> list[dict[str, Any]]:
        """Return all contacts sorted by most recently called."""
        contacts = list(self._contacts.values())
        contacts.sort(key=lambda c: c.get("last_called", ""), reverse=True)
        return contacts

    def delete(self, caller_id: str) -> bool:
        """Remove a contact. Returns True if found and deleted."""
        if caller_id in self._contacts:
            del self._contacts[caller_id]
            self._save()
            return True
        return False

    def greeting_for(self, caller_id: str) -> str | None:
        """Return a personalized greeting hint for the caller, or None."""
        contact = self._contacts.get(caller_id)
        if not contact:
            return None
        name = contact.get("name")
        if name:
            return f"The caller is {name}. Greet them by name."
        return None
