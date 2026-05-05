import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any

import httpx

from secretary_ai.core.config import Settings
from secretary_ai.core.locales import (
    CALENDAR_CREATE_KEYWORDS,
    CALENDAR_DATETIME_FORMAT,
    CALENDAR_DAY_TODAY,
    CALENDAR_DAY_TOMORROW,
    CALENDAR_DELETE_KEYWORDS,
    CALENDAR_EVENT_DONE,
    CALENDAR_EVENT_DUPLICATE,
    CALENDAR_EVENT_LINE,
    CALENDAR_MUTATION_DUPLICATE,
    CALENDAR_MUTATION_KEYWORDS,
    CALENDAR_MUTATION_QUEUED,
    CALENDAR_NO_EVENTS,
    CALENDAR_PLANNER_PROMPT,
    CALENDAR_READ_KEYWORDS,
    CALENDAR_REMINDER_DONE,
    CALENDAR_REMINDER_DUPLICATE,
    CALENDAR_REMINDER_KEYWORDS,
    CALENDAR_TIME_FORMAT,
    CALENDAR_TODAY_KEYWORDS,
    CALENDAR_TOMORROW_KEYWORDS,
    CALENDAR_UNKNOWN_TIME,
    CALENDAR_UNTITLED,
    CALENDAR_UPCOMING_PREFIX,
    WEEKDAY_NAMES,
    t,
)

try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from google_auth_oauthlib.flow import Flow as OAuthFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:  # pragma: no cover - optional dependency
    service_account = None  # type: ignore[assignment]
    OAuthCredentials = None  # type: ignore[assignment]
    OAuthFlow = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    HttpError = Exception  # type: ignore[assignment]

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarService:
    """Two-tier calendar service:

    - Light layer: fast cache reads + enqueue intents.
    - Smart layer: planner worker (LLM or heuristic) processes queue and mutates cache/provider.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._service: Any = None
        self._oauth_state: str | None = None
        self._oauth_state_ts: float = 0.0

        self.cache_path = Path(self.settings.calendar_cache_path)
        self.queue_path = Path(self.settings.calendar_queue_path)

        self.cache: dict[str, Any] = {
            "updated_at": None,
            "events": [],
        }
        self.queue: list[dict[str, Any]] = []
        self._last_mutation_by_call: dict[str, dict[str, Any]] = {}

        self._load_state()

    def readiness(self) -> tuple[bool, str]:
        if not self.settings.calendar_enabled:
            return False, "Calendar integration is disabled by config."

        if build is None:
            return False, "Google Calendar dependencies are not installed in this environment."

        # OAuth token takes priority over service account.
        if self._has_oauth_token():
            if not self.settings.calendar_id:
                return False, "OAuth token found but CALENDAR_ID is not set in .env."
            return True, "Google Calendar integration is configured (OAuth)."

        if not self.settings.calendar_service_account_json or not self.settings.calendar_id:
            if self.settings.google_client_id:
                return (
                    False,
                    "OAuth not yet authorized. Visit /api/v1/calendar/oauth/authorize to connect.",
                )
            return (
                False,
                "Calendar provider credentials not configured; running in cache-only mode.",
            )

        if service_account is None:
            return False, "Google Calendar dependencies are not installed in this environment."

        path = Path(self.settings.calendar_service_account_json)
        if not path.exists():
            return False, f"Service account file not found: {path}"

        return True, "Google Calendar integration is configured (service account)."

    def _has_oauth_token(self) -> bool:
        """Cheap check: token file exists and is parseable JSON with a refresh_token."""
        token_path = Path(self.settings.google_oauth_token_path)
        if not token_path.is_file():
            return False
        try:
            data = json.loads(token_path.read_text(encoding="utf-8"))
            return bool(data.get("refresh_token"))
        except Exception:
            return False

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
                    "reply": t(CALENDAR_NO_EVENTS, self.settings.language),
                    "queued": False,
                }
            lines = [self._event_voice_line(ev) for ev in upcoming]
            reply = t(CALENDAR_UPCOMING_PREFIX, self.settings.language) + " ".join(lines)
            return {
                "status": "served_from_cache",
                "reply": reply,
                "queued": False,
                "events": upcoming,
            }

        if self._is_mutation_query(lower):
            start = self._parse_iso_datetime(str(context.get("start_iso") or ""))
            end = self._parse_iso_datetime(str(context.get("end_iso") or ""))
            if start is None:
                start = self._extract_datetime_from_text(text)
            if start is not None and end is None:
                end = start + timedelta(minutes=30)

            normalized_signature = self._mutation_signature(text=text, start=start)
            if self._is_duplicate_mutation(call_id=call_id, signature=normalized_signature):
                return {
                    "status": "already_queued",
                    "reply": self._build_mutation_reply(text=text, start=start, duplicate=True),
                    "queued": False,
                    "duplicate": True,
                }

            mutation_context = dict(context)
            if start is not None:
                mutation_context["start_iso"] = start.isoformat()
            if end is not None:
                mutation_context["end_iso"] = end.isoformat()

            task = self._enqueue_task(call_id=call_id, transcript=text, context=mutation_context)
            self._record_mutation(call_id=call_id, signature=normalized_signature)
            return {
                "status": "queued",
                "reply": self._build_mutation_reply(text=text, start=start, duplicate=False),
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
                    "call_id": item.get("call_id"),
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
        if self.settings.openai_api_key:
            llm_plan = await self._plan_action_llm(task)
            if llm_plan:
                return llm_plan
        return self._plan_action_heuristic(task)

    async def _plan_action_llm(self, task: dict[str, Any]) -> dict[str, Any]:
        model = self.settings.calendar_smart_model or self.settings.openai_model
        base_url = self.settings.openai_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.1,
            "max_tokens": self.settings.calendar_planner_max_tokens,
            "max_completion_tokens": self.settings.calendar_planner_max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": t(CALENDAR_PLANNER_PROMPT, self.settings.language),
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
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.openai_timeout_seconds) as client:
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
        context = task.get("context") if isinstance(task.get("context"), dict) else {}

        lang = self.settings.language
        delete_kw = CALENDAR_DELETE_KEYWORDS.get(lang, ()) + CALENDAR_DELETE_KEYWORDS.get("en", ())
        if any(token in lower for token in delete_kw):
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

        create_kw = CALENDAR_CREATE_KEYWORDS.get(lang, ()) + CALENDAR_CREATE_KEYWORDS.get("en", ())
        if any(token in lower for token in create_kw):
            context_start = str(context.get("start_iso") or "").strip()
            context_end = str(context.get("end_iso") or "").strip()
            if context_start and context_end:
                start = self._parse_iso_datetime(context_start) or (datetime.now(timezone.utc) + timedelta(days=1))
                end = self._parse_iso_datetime(context_end) or (start + timedelta(minutes=30))
            else:
                parsed_start = self._extract_datetime_from_text(text)
                start = parsed_start or (datetime.now(timezone.utc) + timedelta(days=1))
                if parsed_start is None:
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

    def _is_read_query(self, text: str) -> bool:
        lang = self.settings.language
        for lng in (lang, "en"):
            checks = CALENDAR_READ_KEYWORDS.get(lng, ())
            if any(token in text for token in checks):
                return True
        return False

    def _is_mutation_query(self, text: str) -> bool:
        lang = self.settings.language
        for lng in (lang, "en"):
            checks = CALENDAR_MUTATION_KEYWORDS.get(lng, ())
            if any(token in text for token in checks):
                return True
        return False

    def _event_voice_line(self, ev: dict[str, Any]) -> str:
        lang = self.settings.language
        title = str(ev.get("summary") or t(CALENDAR_UNTITLED, lang))
        start = str(ev.get("start") or "")
        when = start.replace("T", " ")[:16] if start else t(CALENDAR_UNKNOWN_TIME, lang)
        return t(CALENDAR_EVENT_LINE, lang).format(title=title, when=when)

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

    def _extract_datetime_from_text(self, text: str) -> datetime | None:
        lang = self.settings.language
        lower = (text or "").lower()
        base = datetime.now(timezone.utc)
        day_offset = 1
        today_kw = CALENDAR_TODAY_KEYWORDS.get(lang, ()) + CALENDAR_TODAY_KEYWORDS.get("en", ())
        tomorrow_kw = CALENDAR_TOMORROW_KEYWORDS.get(lang, ()) + CALENDAR_TOMORROW_KEYWORDS.get("en", ())
        if any(kw in lower for kw in today_kw):
            day_offset = 0
        elif any(kw in lower for kw in tomorrow_kw):
            day_offset = 1

        lower = lower.replace("a.m.", "am").replace("p.m.", "pm")
        match_ampm = re.search(r"\b(\d{1,2})(?:(?::|\.)(\d{2}))?\s*(am|pm)\b", lower)
        hour: int
        minute: int
        if match_ampm:
            hour = int(match_ampm.group(1))
            minute = int(match_ampm.group(2) or "0")
            ampm = str(match_ampm.group(3) or "").lower()
            if hour == 12:
                hour = 0
            if ampm == "pm":
                hour += 12
        else:
            match_24h = re.search(r"\b(\d{1,2})[:.](\d{2})\b", lower)
            if not match_24h:
                return None
            hour = int(match_24h.group(1))
            minute = int(match_24h.group(2))

        if hour >= 24 or minute >= 60:
            return None

        when = base + timedelta(days=day_offset)
        return when.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _mutation_signature(self, text: str, start: datetime | None) -> str:
        normalized = " ".join((text or "").lower().split())
        normalized = re.sub(r"[^\w: ]+", "", normalized)
        if start is not None:
            rounded = start.replace(second=0, microsecond=0).isoformat()
            return f"{normalized}|{rounded}"
        return normalized

    def _is_duplicate_mutation(self, call_id: str, signature: str) -> bool:
        state = self._last_mutation_by_call.get(call_id) or {}
        if str(state.get("signature") or "") != signature:
            return False
        seen_at = self._parse_iso_datetime(str(state.get("at") or ""))
        if seen_at is None:
            return False
        return (datetime.now(timezone.utc) - seen_at).total_seconds() <= 120

    def _record_mutation(self, call_id: str, signature: str) -> None:
        self._last_mutation_by_call[call_id] = {
            "signature": signature,
            "at": datetime.now(timezone.utc).isoformat(),
        }

    def _build_mutation_reply(self, text: str, start: datetime | None, duplicate: bool) -> str:
        lang = self.settings.language
        lower = (text or "").lower()
        reminder_kw = CALENDAR_REMINDER_KEYWORDS.get(lang, ()) + CALENDAR_REMINDER_KEYWORDS.get("en", ())
        is_reminder = any(token in lower for token in reminder_kw)
        if start is None:
            if duplicate:
                return t(CALENDAR_MUTATION_DUPLICATE, lang)
            return t(CALENDAR_MUTATION_QUEUED, lang)

        when = self._human_datetime_phrase(start)
        if is_reminder:
            if duplicate:
                return t(CALENDAR_REMINDER_DUPLICATE, lang).format(when=when)
            return t(CALENDAR_REMINDER_DONE, lang).format(when=when)
        if duplicate:
            return t(CALENDAR_EVENT_DUPLICATE, lang).format(when=when)
        return t(CALENDAR_EVENT_DONE, lang).format(when=when)

    def _human_datetime_phrase(self, value: datetime) -> str:
        lang = self.settings.language
        now = datetime.now(timezone.utc)
        today = now.date()
        utc_value = value.astimezone(timezone.utc)
        date_value = utc_value.date()
        weekday_names = WEEKDAY_NAMES.get(lang, WEEKDAY_NAMES["en"])
        day_label = weekday_names[utc_value.weekday()]
        if date_value == today:
            day_label = t(CALENDAR_DAY_TODAY, lang)
        elif date_value == (today + timedelta(days=1)):
            day_label = t(CALENDAR_DAY_TOMORROW, lang)
        time_fmt = t(CALENDAR_TIME_FORMAT, lang)
        time_label = utc_value.strftime(time_fmt).lstrip("0") if "%I" in time_fmt else utc_value.strftime(time_fmt)
        return t(CALENDAR_DATETIME_FORMAT, lang).format(day=day_label, time=time_label)

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    def _get_service(self):
        if self._service is not None:
            return self._service
        assert build is not None

        creds = self._load_oauth_credentials()
        if creds is None and service_account is not None:
            sa_path = self.settings.calendar_service_account_json
            if sa_path and Path(sa_path).exists():
                creds = service_account.Credentials.from_service_account_file(
                    sa_path, scopes=CALENDAR_SCOPES,
                )

        if creds is None:
            raise RuntimeError(
                "No calendar credentials available. "
                "Authorize via /api/v1/calendar/oauth/authorize or configure a service account."
            )

        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _load_oauth_credentials(self) -> Any:
        """Load and refresh OAuth credentials from the stored token file."""
        token_path = Path(self.settings.google_oauth_token_path)
        if not token_path.is_file() or OAuthCredentials is None:
            return None
        try:
            token_data = json.loads(token_path.read_text(encoding="utf-8"))
            expiry = None
            if token_data.get("expiry"):
                expiry = datetime.fromisoformat(token_data["expiry"])
            creds = OAuthCredentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id") or self.settings.google_client_id,
                client_secret=token_data.get("client_secret") or self.settings.google_client_secret,
                scopes=token_data.get("scopes", CALENDAR_SCOPES),
                expiry=expiry,
            )
            if creds.expired and creds.refresh_token:
                import google.auth.transport.requests
                creds.refresh(google.auth.transport.requests.Request())
                self._save_oauth_credentials(creds)
            return creds
        except Exception:
            return None

    def _save_oauth_credentials(self, creds: Any) -> None:
        token_path = Path(self.settings.google_oauth_token_path)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or CALENDAR_SCOPES),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
        token_path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")

    def get_oauth_authorize_url(self) -> str | None:
        """Build the Google OAuth authorization URL for the user to visit."""
        if not self.settings.google_client_id or not self.settings.google_client_secret:
            return None
        if OAuthFlow is None:
            return None
        flow = OAuthFlow.from_client_config(
            {
                "web": {
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=CALENDAR_SCOPES,
            redirect_uri=self.settings.google_oauth_redirect_uri,
        )
        url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        self._oauth_state = state
        self._oauth_state_ts = datetime.now(timezone.utc).timestamp()
        return url

    def handle_oauth_callback(self, code: str, state: str | None = None) -> dict[str, Any]:
        """Exchange the authorization code for tokens and persist them."""
        if self._oauth_state is None:
            return {"status": "error", "detail": "No pending OAuth flow. Start at /authorize."}
        elapsed = datetime.now(timezone.utc).timestamp() - self._oauth_state_ts
        if elapsed > 600:
            self._oauth_state = None
            return {"status": "error", "detail": "OAuth flow expired. Please start again."}
        if state != self._oauth_state:
            return {"status": "error", "detail": "Invalid OAuth state — possible CSRF."}
        if not self.settings.google_client_id or not self.settings.google_client_secret:
            return {"status": "error", "detail": "OAuth client credentials not configured."}
        if OAuthFlow is None:
            return {"status": "error", "detail": "google-auth-oauthlib not installed."}
        flow = OAuthFlow.from_client_config(
            {
                "web": {
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=CALENDAR_SCOPES,
            redirect_uri=self.settings.google_oauth_redirect_uri,
        )
        try:
            flow.fetch_token(code=code)
        except Exception as exc:
            return {"status": "error", "detail": f"Token exchange failed: {exc}"}
        creds = flow.credentials
        self._save_oauth_credentials(creds)
        # Reset cached service so next call uses new credentials.
        self._service = None
        self._oauth_state = None
        return {"status": "ok", "detail": "Google Calendar connected successfully."}

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
        except (HttpError, RuntimeError) as exc:
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
        except (HttpError, RuntimeError) as exc:
            return {"error": str(exc)}

    def _delete_event_sync(self, event_id: str) -> dict[str, Any]:
        try:
            svc = self._get_service()
            svc.events().delete(calendarId=self.settings.calendar_id, eventId=event_id).execute()
            return {"id": event_id, "status": "deleted"}
        except (HttpError, RuntimeError) as exc:
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
