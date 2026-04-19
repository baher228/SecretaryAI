import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import httpx

from secretary_ai.core.config import Settings

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:  # pragma: no cover - optional dependency
    service_account = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    HttpError = Exception  # type: ignore[assignment]


class CalendarService:
    """Two-tier calendar service:

    - Light layer: fast cache reads + enqueue intents.
    - Smart layer: planner worker (LLM or heuristic) processes queue and mutates cache/provider.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._service: Any = None

        self.cache_path = Path(self.settings.calendar_cache_path)
        self.queue_path = Path(self.settings.calendar_queue_path)

        self.cache: dict[str, Any] = {
            "updated_at": None,
            "events": [],
        }
        self.queue: list[dict[str, Any]] = []

        self._load_state()

    def readiness(self) -> tuple[bool, str]:
        if not self.settings.calendar_enabled:
            return False, "Calendar integration is disabled by config."

        if not self.settings.calendar_service_account_json or not self.settings.calendar_id:
            return (
                False,
                "Calendar provider credentials not configured; running in cache-only mode.",
            )

        if service_account is None or build is None:
            return False, "Google Calendar dependencies are not installed in this environment."

        path = Path(self.settings.calendar_service_account_json)
        if not path.exists():
            return False, f"Service account file not found: {path}"

        return True, "Google Calendar integration is configured."

    async def refresh_cache(self, days: int = 7, max_results: int = 30) -> dict[str, Any]:
        if not self.settings.calendar_enabled:
            return {"status": "disabled", "detail": "Calendar is disabled."}

        ready, detail = self.readiness()
        if not ready:
            self.cache["updated_at"] = self._now_iso()
            self._persist_cache()
            return {
                "status": "cache_only",
                "detail": detail,
                "events": self.cache.get("events", []),
                "updated_at": self.cache.get("updated_at"),
            }

        events = await asyncio.to_thread(self._list_events_sync, days, max_results)
        self.cache = {
            "updated_at": self._now_iso(),
            "events": events,
        }
        self._persist_cache()
        return {
            "status": "ok",
            "detail": f"Cached {len(events)} events.",
            "events": events,
            "updated_at": self.cache.get("updated_at"),
        }

    def cache_snapshot(self, limit: int = 10) -> dict[str, Any]:
        events = list(self.cache.get("events", []))
        return {
            "updated_at": self.cache.get("updated_at"),
            "events": events[: max(1, limit)],
            "total_events": len(events),
        }

    def queue_snapshot(self, limit: int = 20) -> dict[str, Any]:
        items = self.queue[-max(1, limit) :]
        return {
            "total": len(self.queue),
            "items": items,
        }

    async def quick_reply_or_enqueue(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Light layer behavior for low-latency voice turns.

        - Fast read requests served from cache.
        - Mutating requests are queued for smart planner.
        """

        if not self.settings.calendar_enabled:
            return {"status": "disabled", "detail": "calendar_disabled"}

        context = context or {}
        text = (transcript or "").strip()
        lower = text.lower()

        if not text:
            return {"status": "ignored", "detail": "empty_transcript"}

        if self._is_read_query(lower):
            upcoming = self._upcoming_events(limit=3)
            if not upcoming:
                return {
                    "status": "served_from_cache",
                    "reply": "I don’t see upcoming calendar events in cache right now.",
                    "queued": False,
                }
            lines = [self._event_voice_line(ev) for ev in upcoming]
            reply = "Upcoming: " + " ".join(lines)
            return {
                "status": "served_from_cache",
                "reply": reply,
                "queued": False,
                "events": upcoming,
            }

        if self._is_mutation_query(lower):
            task = self._enqueue_task(call_id=call_id, transcript=text, context=context)
            return {
                "status": "queued",
                "reply": "Got it. I queued this calendar request and will apply it shortly.",
                "queued": True,
                "task_id": task["task_id"],
            }

        return {"status": "ignored", "detail": "no_calendar_intent"}

    async def process_queue(self, max_items: int = 5) -> dict[str, Any]:
        if not self.settings.calendar_enabled:
            return {"status": "disabled", "processed": 0, "results": []}

        processed = 0
        results: list[dict[str, Any]] = []

        async with self._lock:
            for item in self.queue:
                if processed >= max(1, max_items):
                    break
                if item.get("status") != "queued":
                    continue

                item["status"] = "processing"
                plan = await self._plan_action(item)
                apply_result = await self._apply_plan(plan)
                item["status"] = "done" if apply_result.get("status") in {"ok", "cache_only"} else "failed"
                item["plan"] = plan
                item["result"] = apply_result
                item["processed_at"] = self._now_iso()

                processed += 1
                results.append({
                    "task_id": item.get("task_id"),
                    "status": item.get("status"),
                    "plan": plan,
                    "result": apply_result,
                })

            self._persist_queue()

        return {"status": "ok", "processed": processed, "results": results}

    def _enqueue_task(self, call_id: str, transcript: str, context: dict[str, Any]) -> dict[str, Any]:
        task_id = f"cal-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{len(self.queue)+1}"
        task = {
            "task_id": task_id,
            "call_id": call_id,
            "transcript": transcript,
            "context": context,
            "status": "queued",
            "created_at": self._now_iso(),
        }
        self.queue.append(task)
        self._persist_queue()
        return task

    async def _plan_action(self, task: dict[str, Any]) -> dict[str, Any]:
        if self.settings.zai_api_key:
            llm_plan = await self._plan_action_llm(task)
            if llm_plan:
                return llm_plan
        return self._plan_action_heuristic(task)

    async def _plan_action_llm(self, task: dict[str, Any]) -> dict[str, Any]:
        model = self.settings.calendar_smart_model or self.settings.zai_model
        base_url = self.settings.zai_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.1,
            "max_tokens": self.settings.calendar_planner_max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a calendar planner. Return ONLY JSON. "
                        "Schema: {action: create|delete|none, title: string|null, "
                        "start_iso: string|null, end_iso: string|null, event_id: string|null, reason: string}. "
                        "If no safe mutation can be inferred, return action=none."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "transcript": task.get("transcript"),
                            "context": task.get("context", {}),
                            "timezone": self.settings.calendar_timezone,
                        }
                    ),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.zai_api_key}",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en",
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.zai_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 300:
                return {}
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return {}
            message = choices[0].get("message") or {}
            raw = str(message.get("content") or "").strip()
            if not raw:
                return {}
            parsed = self._try_parse_json(raw)
            if not parsed:
                return {}
            action = str(parsed.get("action") or "none").strip().lower()
            if action not in {"create", "delete", "none"}:
                action = "none"
            return {
                "action": action,
                "title": parsed.get("title"),
                "start_iso": parsed.get("start_iso"),
                "end_iso": parsed.get("end_iso"),
                "event_id": parsed.get("event_id"),
                "reason": parsed.get("reason") or "planned_by_llm",
                "planner_model": model,
            }
        except Exception:
            return {}

    def _plan_action_heuristic(self, task: dict[str, Any]) -> dict[str, Any]:
        text = str(task.get("transcript") or "").strip()
        lower = text.lower()

        if any(token in lower for token in ("delete", "remove", "cancel event")):
            event_id = self._extract_event_id(lower)
            return {
                "action": "delete",
                "event_id": event_id,
                "title": None,
                "start_iso": None,
                "end_iso": None,
                "reason": "heuristic_delete",
                "planner_model": "heuristic",
            }

        if any(token in lower for token in ("schedule", "book", "add to calendar", "create event")):
            start = datetime.now(timezone.utc) + timedelta(days=1)
            start = start.replace(hour=10, minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=30)
            title = self._title_from_text(text)
            return {
                "action": "create",
                "title": title,
                "start_iso": start.isoformat(),
                "end_iso": end.isoformat(),
                "event_id": None,
                "reason": "heuristic_create",
                "planner_model": "heuristic",
            }

        return {
            "action": "none",
            "title": None,
            "start_iso": None,
            "end_iso": None,
            "event_id": None,
            "reason": "heuristic_none",
            "planner_model": "heuristic",
        }

    async def _apply_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        action = str(plan.get("action") or "none")
        if action == "none":
            return {"status": "ignored", "detail": "No safe action inferred."}

        ready, detail = self.readiness()
        if action == "create":
            title = str(plan.get("title") or "Untitled")
            start_iso = str(plan.get("start_iso") or "")
            end_iso = str(plan.get("end_iso") or "")
            if not start_iso or not end_iso:
                return {"status": "error", "detail": "Missing start/end for create action."}

            if ready:
                created = await asyncio.to_thread(self._create_event_sync, title, start_iso, end_iso)
                if created.get("error"):
                    return {"status": "error", "detail": str(created.get("error"))}
                self._upsert_cache_event(created)
                self._persist_cache()
                return {"status": "ok", "detail": "Event created in provider.", "event": created}

            cached = {
                "id": f"cached-{int(datetime.now(timezone.utc).timestamp())}",
                "summary": title,
                "start": start_iso,
                "end": end_iso,
                "description": "cached_only",
                "location": None,
                "attendees": [],
                "html_link": None,
            }
            self._upsert_cache_event(cached)
            self._persist_cache()
            return {"status": "cache_only", "detail": detail, "event": cached}

        if action == "delete":
            event_id = str(plan.get("event_id") or "").strip()
            if not event_id:
                return {"status": "error", "detail": "Missing event_id for delete action."}

            if ready:
                deleted = await asyncio.to_thread(self._delete_event_sync, event_id)
                if deleted.get("error"):
                    return {"status": "error", "detail": str(deleted.get("error"))}

            events = [ev for ev in self.cache.get("events", []) if str(ev.get("id")) != event_id]
            self.cache["events"] = events
            self.cache["updated_at"] = self._now_iso()
            self._persist_cache()
            return {"status": "ok" if ready else "cache_only", "detail": "Event removed.", "event_id": event_id}

        return {"status": "error", "detail": f"Unsupported action: {action}"}

    def _upcoming_events(self, limit: int = 3) -> list[dict[str, Any]]:
        events = list(self.cache.get("events", []))
        now = datetime.now(timezone.utc)

        def start_dt(ev: dict[str, Any]) -> datetime:
            raw = str(ev.get("start") or "")
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                return now + timedelta(days=3650)

        sorted_events = sorted(events, key=start_dt)
        out: list[dict[str, Any]] = []
        for ev in sorted_events:
            s = start_dt(ev)
            if s >= now - timedelta(hours=2):
                out.append(ev)
            if len(out) >= max(1, limit):
                break
        return out

    @staticmethod
    def _is_read_query(text: str) -> bool:
        checks = (
            "what\'s on my calendar",
            "whats on my calendar",
            "what is on my calendar",
            "calendar today",
            "calendar tomorrow",
            "my next meeting",
            "upcoming events",
            "show calendar",
        )
        return any(token in text for token in checks)

    @staticmethod
    def _is_mutation_query(text: str) -> bool:
        checks = (
            "add to calendar",
            "create event",
            "schedule",
            "book",
            "reschedule",
            "delete event",
            "cancel event",
            "remove event",
        )
        return any(token in text for token in checks)

    @staticmethod
    def _event_voice_line(ev: dict[str, Any]) -> str:
        title = str(ev.get("summary") or "untitled")
        start = str(ev.get("start") or "")
        when = start.replace("T", " ")[:16] if start else "unknown time"
        return f"{title} at {when}."

    @staticmethod
    def _extract_event_id(text: str) -> str | None:
        marker = "event "
        if marker not in text:
            return None
        idx = text.find(marker)
        tail = text[idx + len(marker) :].strip()
        if not tail:
            return None
        return tail.split()[0].strip(".,")

    @staticmethod
    def _title_from_text(text: str) -> str:
        compact = " ".join(text.split()).strip()
        if len(compact) <= 60:
            return compact
        return compact[:57].rstrip() + "..."

    def _get_service(self):
        if self._service is not None:
            return self._service
        assert service_account is not None and build is not None
        creds = service_account.Credentials.from_service_account_file(
            self.settings.calendar_service_account_json,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _list_events_sync(self, days: int, max_results: int) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        t_min = now.isoformat()
        t_max = (now + timedelta(days=max(1, days))).isoformat()
        try:
            svc = self._get_service()
            resp = (
                svc.events()
                .list(
                    calendarId=self.settings.calendar_id,
                    timeMin=t_min,
                    timeMax=t_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return [self._event_to_dict(e) for e in resp.get("items", [])]
        except HttpError as exc:
            return [{"error": str(exc)}]

    def _create_event_sync(self, title: str, start_iso: str, end_iso: str) -> dict[str, Any]:
        body = {
            "summary": title,
            "start": {"dateTime": start_iso, "timeZone": self.settings.calendar_timezone},
            "end": {"dateTime": end_iso, "timeZone": self.settings.calendar_timezone},
        }
        try:
            svc = self._get_service()
            ev = svc.events().insert(calendarId=self.settings.calendar_id, body=body).execute()
            return self._event_to_dict(ev)
        except HttpError as exc:
            return {"error": str(exc)}

    def _delete_event_sync(self, event_id: str) -> dict[str, Any]:
        try:
            svc = self._get_service()
            svc.events().delete(calendarId=self.settings.calendar_id, eventId=event_id).execute()
            return {"id": event_id, "status": "deleted"}
        except HttpError as exc:
            return {"error": str(exc)}

    def _upsert_cache_event(self, event: dict[str, Any]) -> None:
        events = [ev for ev in self.cache.get("events", []) if str(ev.get("id")) != str(event.get("id"))]
        events.append(event)
        self.cache["events"] = events
        self.cache["updated_at"] = self._now_iso()

    @staticmethod
    def _event_to_dict(ev: dict) -> dict:
        return {
            "id": ev.get("id"),
            "summary": ev.get("summary"),
            "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
            "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
            "description": ev.get("description"),
            "location": ev.get("location"),
            "attendees": [a.get("email") for a in ev.get("attendees", []) if a.get("email")],
            "html_link": ev.get("htmlLink"),
        }

    @staticmethod
    def _try_parse_json(raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if not text:
            return {}
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
            return {}

    def _load_state(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

        if self.cache_path.exists():
            try:
                loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.cache = {
                        "updated_at": loaded.get("updated_at"),
                        "events": loaded.get("events") if isinstance(loaded.get("events"), list) else [],
                    }
            except Exception:
                pass

        if self.queue_path.exists():
            try:
                loaded = json.loads(self.queue_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    self.queue = loaded
            except Exception:
                pass

    def _persist_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _persist_queue(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(self.queue, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
