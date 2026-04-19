import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings


class LiveDebugLogger:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(self.settings.telegram_live_debug_log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

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
        except Exception:
            return
