import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings

MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB


class LiveDebugLogger:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(self.settings.telegram_live_debug_log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_count = 0

    def log(self, call_id: str, stage: str, data: dict[str, Any] | None = None) -> None:
        if not self.settings.telegram_live_debug:
            return
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "call_id": call_id,
            "stage": stage,
            "data": data or {},
        }
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._write_count += 1
            if self._write_count % 500 == 0:
                self._rotate_if_needed()
        except Exception:
            return

    def _rotate_if_needed(self) -> None:
        try:
            if not self.path.exists():
                return
            if self.path.stat().st_size < MAX_LOG_BYTES:
                return
            rotated = self.path.with_suffix(".jsonl.old")
            rotated.unlink(missing_ok=True)
            self.path.rename(rotated)
        except Exception:
            return
