import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import re

from secretary_ai.core.config import Settings


class MemoryStore:
    """Three-tier memory for secretary runtime.

    - short_term: in-call rolling context/transcripts
    - mid_term: near-future event/task focus
    - long_term: append-only durable records
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        root = Path(settings.telegram_audio_root).parent / "memory"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root

        self.short_path = self.root / "short_term.json"
        self.mid_path = self.root / "mid_term.json"
        self.long_path = self.root / "long_term.jsonl"

        self.short_term: dict[str, Any] = self._load_json(self.short_path, default={"calls": {}})
        self.mid_term: dict[str, Any] = self._load_json(self.mid_path, default={"upcoming": [], "updated_at": None})

    def append_long_term(self, record_type: str, payload: dict[str, Any]) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": record_type,
            "payload": payload,
        }
        with self.long_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def add_short_term_turn(self, call_id: str, transcript: str, reply: str | None = None) -> None:
        calls = self.short_term.setdefault("calls", {})
        call = calls.setdefault(call_id, {"turns": [], "updated_at": None})
        turn = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "transcript": transcript,
            "reply": reply,
        }
        turns = call.setdefault("turns", [])
        turns.append(turn)
        # keep short-term bounded
        if len(turns) > 30:
            call["turns"] = turns[-30:]
        call["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_json(self.short_path, self.short_term)

    def prune_short_term(self, max_age_hours: int = 24) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, max_age_hours))
        calls = self.short_term.setdefault("calls", {})
        keep: dict[str, Any] = {}
        for call_id, data in calls.items():
            updated_at = str((data or {}).get("updated_at") or "")
            try:
                dt = datetime.fromisoformat(updated_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)
            if dt >= cutoff:
                keep[call_id] = data
        self.short_term["calls"] = keep
        self._save_json(self.short_path, self.short_term)

    def set_mid_term_upcoming(self, events: list[dict[str, Any]]) -> None:
        self.mid_term = {
            "upcoming": events[:50],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_json(self.mid_path, self.mid_term)

    def snapshot(self) -> dict[str, Any]:
        calls = self.short_term.get("calls", {}) if isinstance(self.short_term, dict) else {}
        return {
            "short_term": {
                "active_calls": len(calls),
                "path": str(self.short_path),
            },
            "mid_term": {
                "upcoming_count": len(self.mid_term.get("upcoming", [])) if isinstance(self.mid_term, dict) else 0,
                "updated_at": (self.mid_term or {}).get("updated_at") if isinstance(self.mid_term, dict) else None,
                "path": str(self.mid_path),
            },
            "long_term": {
                "path": str(self.long_path),
            },
        }

    def add_user_fact_if_requested(self, call_id: str, transcript: str) -> dict[str, Any] | None:
        text = " ".join((transcript or "").split()).strip()
        lower = text.lower()
        if not text:
            return None

        triggers = ("remember that", "remember this", "note that", "write this down", "don't forget", "dont forget")
        if not any(t in lower for t in triggers):
            return None

        fact = text
        for t in triggers:
            idx = lower.find(t)
            if idx >= 0:
                fact = text[idx + len(t) :].strip(" .,:;") or text
                break

        record = {
            "call_id": call_id,
            "fact": fact,
            "kind": "user_fact",
        }
        self.append_long_term("user_fact", record)
        return record

    def retrieve_user_fact(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        query_text = " ".join((query or "").split()).strip().lower()
        if not query_text or not self.long_path.exists():
            return []

        query_tokens = set(re.findall(r"[a-z0-9]+", query_text))
        if not query_tokens:
            return []

        matches: list[tuple[int, dict[str, Any]]] = []
        try:
            for line in self.long_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if str(row.get("type")) != "user_fact":
                    continue
                payload = row.get("payload") or {}
                fact = str(payload.get("fact") or "")
                tokens = set(re.findall(r"[a-z0-9]+", fact.lower()))
                score = len(query_tokens.intersection(tokens))
                if score > 0:
                    matches.append((score, {"fact": fact, "ts": row.get("ts"), "call_id": payload.get("call_id")}))
        except Exception:
            return []

        matches.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in matches[: max(1, limit)]]

    @staticmethod
    def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else default
        except Exception:
            return default

    @staticmethod
    def _save_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
