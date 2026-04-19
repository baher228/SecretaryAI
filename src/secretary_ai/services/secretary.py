import asyncio
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
from time import monotonic
from typing import Any

import httpx

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import (
    AgentLiveRespondResponse,
    AgentAnalyzeResponse,
    AgentReplyResponse,
    ArchitectureOverview,
    CalendarCacheResponse,
    CalendarProcessResponse,
    CalendarQueueRequest,
    CalendarQueueResponse,
    CalendarQueueSnapshotResponse,
    CallAudioPlayRequest,
    CallAudioRecordRequest,
    CallAudioResponse,
    CallEventAck,
    CallTranscriptRequest,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    InboundCallResponse,
    ModelCheckResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    PostCallEventRequest,
    PostCallSummary,
    TelegramAuthSendCodeResponse,
    TelegramAuthSignInResponse,
    TelegramLiveAgentResponse,
    TelegramLiveAgentStartRequest,
    TelegramLiveAgentStatusResponse,
    TelegramAuthStatusResponse,
)
from secretary_ai.services.ai_agent import SecretaryAIAgent
from secretary_ai.services.calendar import CalendarService
from secretary_ai.services.live_debug import LiveDebugLogger
from secretary_ai.services.live_templates import LiveTemplateMatcher
from secretary_ai.services.memory_store import MemoryStore
from secretary_ai.services.stt import STTEngine
from secretary_ai.services.telegram_calls import TelegramCallService
from secretary_ai.services.tts import TTSEngine
from secretary_ai.services.maps import MapService
from secretary_ai.services.booking import BookingService


class SecretaryService:
    """Main orchestrator: Z.AI reasoning + Telegram MTProto call provider."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.telegram = TelegramCallService(settings)
        self.calendar = CalendarService(settings)
        self.ai = SecretaryAIAgent(settings)
        self.template_matcher = LiveTemplateMatcher(settings)
        self.memory = MemoryStore(settings)
        self.debug = LiveDebugLogger(settings)
        self.tts = TTSEngine(settings)
        self.stt = STTEngine(settings)
        self.maps = MapService(settings)
        self.booking = BookingService(settings)
        self.live_sessions: dict[str, dict[str, Any]] = {}
        self._auto_live_task: asyncio.Task | None = None
        self._calendar_worker_task: asyncio.Task | None = None
        self._template_audio_cache: dict[str, str] = {}
        self._reminder_flow_state: dict[str, dict[str, Any]] = {}

    async def startup(self) -> None:
        await self.telegram.start()
        await self.calendar.refresh_cache()
        self.memory.prune_short_term(max_age_hours=24)
        self.memory.set_mid_term_upcoming(self.calendar.cache_snapshot(limit=50).get("events", []))

        if self.settings.stt_prewarm_on_startup:
            try:
                await asyncio.wait_for(asyncio.to_thread(self.stt._ensure_model), timeout=45.0)  # type: ignore[attr-defined]
                self.debug.log("system", "stt_prewarm_ok", {"model": self.settings.stt_model})
            except Exception as exc:
                self.debug.log("system", "stt_prewarm_failed", {"error": exc.__class__.__name__, "detail": str(exc)})

        if self.settings.telegram_auto_start_live_agent:
            self._auto_live_task = asyncio.create_task(self._auto_attach_live_loop())
        if self.settings.calendar_worker_enabled:
            self._calendar_worker_task = asyncio.create_task(self._calendar_worker_loop())

    async def shutdown(self) -> None:
        await self._stop_auto_live_task()
        await self._stop_calendar_worker_task()
        await self._stop_all_live_sessions()
        await self.telegram.stop()

    def architecture_overview(self) -> ArchitectureOverview:
        return ArchitectureOverview(
            name="Secretary AI",
            mode="telegram_mtproto_mvp",
            components=[
                "API Layer (FastAPI routes)",
                "Telegram MTProto (Telethon user session)",
                "Telegram Calls Engine (py-tgcalls private calls)",
                "AI Orchestrator (intent + response + actions)",
                "STT Adapter (faster-whisper)",
                "TTS Adapter (assistant voice generation)",
                "Telegram Live Loop (recording -> STT -> AI -> TTS)",
                "Secretary Orchestrator (this service)",
                "Z.AI Reasoning Endpoint",
                "Storage Layer (in-memory MVP)",
            ],
            notes=(
                "Experimental hackathon stack using a real Telegram user account session. "
                "Designed for easy provider swap to Twilio/others later."
            ),
        )

    async def check_model_connection(self, prompt: str) -> ModelCheckResponse:
        if not self.settings.zai_api_key:
            return ModelCheckResponse(
                model=self.settings.zai_model,
                connected=False,
                detail="Missing ZAI_API_KEY in environment.",
            )
        payload = {
            "model": self.settings.zai_model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 100,
        }
        result = await self._zai_chat_completion(payload)
        if result.get("error"):
            return ModelCheckResponse(
                model=self.settings.zai_model,
                connected=False,
                detail=result["error"],
                output=result.get("raw"),
            )
        message = self._extract_message(result["data"])
        return ModelCheckResponse(
            model=self.settings.zai_model,
            connected=True,
            detail="Connected to Z.AI GLM successfully.",
            output=message.get("content"),
        )

    async def chat_direct(self, payload: ChatRequest) -> ChatResponse:
        """Direct conversational chat with Z.AI - no call context, plain text reply."""
        chat_model = self.settings.zai_chat_model or self.settings.zai_model
        system_prompt = (
            "You are Secretary AI. "
            "Reply with short, direct, practical answers. "
            "Prefer 1 to 2 short sentences and avoid fluff. "
            "Only add detail if the user explicitly asks for it. "
            "Return ONLY the final assistant reply text for the user. "
            "Do not reveal reasoning, internal analysis, instructions, or policy notes."
        )
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in payload.history[-20:]:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": payload.message})

        if not self.settings.zai_api_key:
            reply = "ZAI_API_KEY is not configured. Please add it to your .env file."
        else:
            api_payload = {
                "model": chat_model,
                "messages": messages,
                "temperature": self.settings.chat_temperature,
                "max_tokens": self.settings.chat_max_tokens,
            }
            result = await self._zai_chat_completion(api_payload)
            if result.get("error"):
                reply = f"AI error: {result['error']}"
            else:
                msg_data = self._extract_message(result["data"])
                reply = self._extract_text_from_content(msg_data.get("content"))
                if not reply:
                    retry_messages = [
                        {
                            "role": "system",
                            "content": (
                                "Reply in one short sentence only. "
                                "Final answer only. No analysis."
                            ),
                        },
                        {"role": "user", "content": payload.message},
                    ]
                    retry_payload = {
                        "model": chat_model,
                        "messages": retry_messages,
                        "temperature": 0.1,
                        "max_tokens": max(18, min(48, int(self.settings.chat_max_tokens))),
                    }
                    retry_result = await self._zai_chat_completion(retry_payload)
                    if not retry_result.get("error"):
                        retry_msg = self._extract_message(retry_result["data"])
                        reply = self._extract_text_from_content(retry_msg.get("content"))

                reply = self._normalize_chat_reply(reply)
                if not reply:
                    reply = self._fallback_short_reply(payload.message)

        new_history = list(payload.history) + [
            ChatMessage(role="user", content=payload.message),
            ChatMessage(role="assistant", content=reply),
        ]
        return ChatResponse(
            reply=reply,
            model=chat_model,
            history=new_history[-40:],
        )

    @staticmethod
    def _normalize_chat_reply(reply: str) -> str:
        text = " ".join((reply or "").split()).strip()
        if not text:
            return ""

        lower = text.lower()
        meta_markers = [
            "i'm instructed",
            "i am instructed",
            "the user",
            "my response should be",
            "this is:",
            "i should",
            "without fluff",
            "short and direct",
        ]
        has_meta = any(marker in lower for marker in meta_markers)

        if has_meta:
            quoted = re.findall(r"['\"“”]([^'\"“”]{2,180})['\"“”]", text)
            if quoted:
                candidate = quoted[-1].strip()
                if candidate:
                    text = candidate
            else:
                for marker in ("my response should be:", "response would be:", "appropriate response would be:"):
                    idx = lower.find(marker)
                    if idx >= 0:
                        text = text[idx + len(marker) :].strip()
                        break
                for stopper in (" this is:", " - ", " only add detail", " i should"):
                    idx = text.lower().find(stopper)
                    if idx > 0:
                        text = text[:idx].strip()

        # Keep spoken replies short and natural.
        if len(text) > 180:
            parts = re.split(r"(?<=[.!?])\s+", text)
            text = " ".join(parts[:2]).strip()
        if len(text) > 180:
            text = text[:177].rstrip() + "..."
        return text

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, dict):
            for key in ("text", "content", "value", "output_text"):
                value = content.get(key)
                extracted = SecretaryService._extract_text_from_content(value)
                if extracted:
                    return extracted
            return ""
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                extracted = SecretaryService._extract_text_from_content(item)
                if extracted:
                    parts.append(extracted)
            return " ".join(parts).strip()
        return str(content).strip()

    @staticmethod
    def _fallback_short_reply(user_message: str) -> str:
        text = (user_message or "").strip().lower()
        if any(token in text for token in ("hello", "hi", "hey")):
            return "Hello. How can I help?"
        if "how are you" in text:
            return "I'm good, thanks. How can I help?"
        return "Understood. Tell me what you need, and I'll keep it brief."

    async def telegram_auth_status(self) -> TelegramAuthStatusResponse:
        payload = await self.telegram.auth_status()
        return TelegramAuthStatusResponse(**payload)

    async def telegram_send_code(self, phone_number: str) -> TelegramAuthSendCodeResponse:
        payload = await self.telegram.send_code(phone_number)
        return TelegramAuthSendCodeResponse(**payload)

    async def telegram_sign_in(
        self,
        phone_number: str,
        code: str | None,
        phone_code_hash: str | None,
        password: str | None,
    ) -> TelegramAuthSignInResponse:
        payload = await self.telegram.sign_in(
            phone_number=phone_number,
            code=code,
            phone_code_hash=phone_code_hash,
            password=password,
        )
        return TelegramAuthSignInResponse(**payload)

    async def start_outbound_call(self, payload: OutboundCallRequest) -> OutboundCallResponse:
        result = await self.telegram.start_outbound_call(
            target_user=payload.target_user,
            purpose=payload.purpose.value,
            initial_audio_path=payload.initial_audio_path,
            metadata=payload.metadata,
        )
        response = OutboundCallResponse(**result)
        should_greet = (
            response.status == "active"
            and bool(response.call_id)
            and not payload.initial_audio_path
            and bool(self.settings.assistant_auto_greet_on_connect)
        )
        if should_greet:
            greeting = await self._play_greeting_with_retry(response.call_id, source="outbound")
            response.detail = (
                f"{response.detail} Greeting: {greeting.get('status')} "
                f"({greeting.get('detail')})."
            )

        should_auto_live = (
            response.status == "active"
            and bool(response.call_id)
            and bool(self.settings.telegram_auto_start_live_agent)
        )
        if should_auto_live:
            auto_live = await self.start_telegram_live_agent(
                response.call_id,
                TelegramLiveAgentStartRequest(
                    context={"source": "outbound_auto_start"},
                    speak_response=self.settings.telegram_auto_start_live_speak_response,
                ),
            )
            response.detail = f"{response.detail} Live loop: {auto_live.status}."
        return response

    async def append_transcript(self, call_id: str, payload: CallTranscriptRequest) -> InboundCallResponse:
        self.telegram.append_transcript(call_id, payload.transcript, metadata=payload.metadata)
        return InboundCallResponse(
            call_id=call_id,
            status="received",
            detail="Transcript accepted and stored.",
        )

    async def finalize_call(self, payload: PostCallEventRequest) -> PostCallSummary:
        self.telegram.append_transcript(payload.call_id, payload.transcript, metadata=payload.metadata)
        call = self.telegram.get_call(payload.call_id) or {}
        call["status"] = "completed"
        return PostCallSummary(
            call_id=payload.call_id,
            status="completed",
            detail="Post-call event stored.",
        )

    async def generate_agent_reply(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any],
    ) -> AgentReplyResponse:
        analysis = await self.analyze_agent_turn(call_id=call_id, transcript=transcript, context=context)
        return AgentReplyResponse(
            call_id=call_id,
            reply=analysis.reply,
            action_items=analysis.action_items,
        )

    async def live_agent_respond(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any],
        speak_response: bool,
    ) -> AgentLiveRespondResponse:
        fact_record = self.memory.add_user_fact_if_requested(call_id=call_id, transcript=transcript)
        if fact_record is not None:
            remember_reply = f"Got it. I wrote it down: {fact_record.get('fact')}"
            return await self._fast_fallback_response(
                call_id=call_id,
                snippet=transcript,
                reply=remember_reply,
                action_item="memory_write",
                speak_response=speak_response,
            )

        retrieval_hits = self.memory.retrieve_user_fact(transcript, limit=1)
        if retrieval_hits and any(k in transcript.lower() for k in ("remember", "what did i", "about me", "my favorite", "what do i")):
            recalled = str(retrieval_hits[0].get("fact") or "")
            recall_reply = f"You told me: {recalled}"
            return await self._fast_fallback_response(
                call_id=call_id,
                snippet=transcript,
                reply=recall_reply,
                action_item="memory_recall",
                speak_response=speak_response,
            )

        calendar_turn = await self.calendar.quick_reply_or_enqueue(
            call_id=call_id,
            transcript=transcript,
            context=context,
        )

        forced_reply = calendar_turn.get("reply") if isinstance(calendar_turn, dict) else None
        template_hit = self.template_matcher.match(transcript) if not forced_reply else None

        if forced_reply or template_hit:
            self.debug.log(
                call_id,
                "template_or_forced_reply",
                {
                    "forced_reply": bool(forced_reply),
                    "template_hit": template_hit,
                    "transcript": transcript[:160],
                },
            )

            template_id = str((template_hit or {}).get("id") or "") if template_hit else ""
            if template_id == "reminder_set":
                return await self._handle_reminder_flow(call_id=call_id, transcript=transcript, speak_response=speak_response)

            # Critical for latency: do NOT run remote analysis when we already have deterministic reply.
            selected_reply = str(forced_reply or (template_hit or {}).get("reply") or "")
            analysis = AgentAnalyzeResponse(
                call_id=call_id,
                reply=selected_reply,
                model=self.settings.zai_model,
            )
            action_items: list[str] = []

            if template_hit and not forced_reply:
                action_items.append(f"template_reply:{template_hit.get('id')}")
                if bool(template_hit.get("calendar_check")):
                    snapshot = self.calendar.cache_snapshot(limit=3)
                    action_items.append(f"calendar_checked:{snapshot.get('total_events', 0)}")
                if bool(template_hit.get("calendar_enqueue")):
                    queued = await self.calendar.quick_reply_or_enqueue(
                        call_id=call_id,
                        transcript=transcript,
                        context={**context, "source": "template_enqueue"},
                    )
                    if bool(queued.get("queued")):
                        action_items.append(f"calendar_queue:{queued.get('task_id')}")

            if bool(calendar_turn.get("queued")):
                action_items.append(f"calendar_queue:{calendar_turn.get('task_id')}")

            analysis.action_items = action_items[:8]
            self.memory.add_short_term_turn(call_id=call_id, transcript=transcript, reply=analysis.reply)
            self.memory.append_long_term(
                "live_turn_template",
                {
                    "call_id": call_id,
                    "transcript": transcript,
                    "reply": analysis.reply,
                    "source": "calendar_forced" if forced_reply else "template",
                    "template_id": (template_hit or {}).get("id") if template_hit else None,
                    "actions": analysis.action_items,
                },
            )

            if template_id:
                if template_id in self._template_audio_cache:
                    tts_audio_path = self._template_audio_cache[template_id]
                    tts_status = "cached"
                else:
                    tts_audio_path, tts_status = await self.tts.synthesize(analysis.reply, call_id=f"template-{template_id}")
                    if tts_audio_path:
                        self._template_audio_cache[template_id] = tts_audio_path

                call_audio_status = "not_streamed"
                if speak_response and tts_audio_path:
                    stream_result = await self.telegram.stream_audio_out(call_id, tts_audio_path)
                    call_audio_status = str(stream_result.get("status"))

                response = AgentLiveRespondResponse(
                    call_id=call_id,
                    transcript=transcript,
                    reply=analysis.reply,
                    intent=analysis.intent,
                    confidence=analysis.confidence,
                    requires_human=analysis.requires_human,
                    transfer_reason=analysis.transfer_reason,
                    action_items=analysis.action_items,
                    extracted_fields=analysis.extracted_fields,
                    model=analysis.model,
                    tts_audio_path=tts_audio_path,
                    tts_status=tts_status,
                    call_audio_status=call_audio_status,
                )
                return response
        else:
            try:
                analysis = await asyncio.wait_for(
                    self.analyze_agent_turn(call_id=call_id, transcript=transcript, context=context),
                    timeout=max(0.9, float(self.settings.agent_live_timeout_seconds)),
                )
            except asyncio.TimeoutError:
                analysis = AgentAnalyzeResponse(
                    call_id=call_id,
                    reply="Sorry, I’m slow right now. Please repeat in one short sentence.",
                    model=self.settings.zai_model,
                    action_items=["latency_fallback"],
                )

        tts_audio_path: str | None = None
        tts_status: str | None = None
        call_audio_status: str | None = None
        if speak_response:
            tts_audio_path, tts_status = await self.tts.synthesize(analysis.reply, call_id=call_id)
            if tts_audio_path:
                stream_result = await self.telegram.stream_audio_out(call_id, tts_audio_path)
                call_audio_status = str(stream_result.get("status"))
            else:
                call_audio_status = "not_streamed"

            if call_audio_status == "streaming_out":
                session = self.live_sessions.get(call_id)
                if session is not None:
                    cooldown = max(0.2, float(self.settings.telegram_live_tts_cooldown_seconds))
                    session["pause_until"] = datetime.now(timezone.utc) + timedelta(seconds=cooldown)
                    session["last_call_audio_status"] = call_audio_status

        response = AgentLiveRespondResponse(
            call_id=call_id,
            transcript=transcript,
            reply=analysis.reply,
            intent=analysis.intent,
            confidence=analysis.confidence,
            requires_human=analysis.requires_human,
            transfer_reason=analysis.transfer_reason,
            action_items=analysis.action_items,
            extracted_fields=analysis.extracted_fields,
            model=analysis.model,
            tts_audio_path=tts_audio_path,
            tts_status=tts_status,
            call_audio_status=call_audio_status,
        )
        
        # Async process bookings or routes
        raw_intent = analysis.intent.value
        if raw_intent == "plan_route":
            origin = analysis.extracted_fields.get("origin", "London")
            dest = analysis.extracted_fields.get("destination", "Manchester")
            # In a real setup, we would queue this and call back. For demo, we do it inline or log
            asyncio.create_task(self.maps.plan_route(origin, dest))
        elif raw_intent == "search_booking":
            location = analysis.extracted_fields.get("location", "London")
            booking_type = analysis.extracted_fields.get("topic", "restaurants")
            if "hotel" in booking_type:
                asyncio.create_task(self.booking.search_hotels(location, "2026-05-01", "2026-05-05"))
            else:
                asyncio.create_task(self.booking.search_restaurants(location))

        self.memory.add_short_term_turn(call_id=call_id, transcript=transcript, reply=response.reply)
        self.memory.append_long_term(
            "live_turn",
            {
                "call_id": call_id,
                "transcript": transcript,
                "reply": response.reply,
                "intent": response.intent.value,
                "confidence": response.confidence,
            },
        )
        return response

    async def analyze_agent_turn(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any],
    ) -> AgentAnalyzeResponse:
        self.telegram.append_transcript(call_id, transcript, metadata=context)
        self.memory.add_short_term_turn(call_id=call_id, transcript=transcript)
        live_mode = str((context or {}).get("source") or "") == "telegram_live_loop"
        if live_mode:
            analysis = await self.ai.analyze_turn_live(call_id=call_id, transcript=transcript, context=context)
        else:
            analysis = await self.ai.analyze_turn(call_id=call_id, transcript=transcript, context=context)

        call = self.telegram.get_call(call_id)
        if call is not None:
            call["last_agent_analysis"] = analysis.model_dump()
            call["last_agent_reply"] = analysis.reply
            call["last_action_items"] = analysis.action_items
            call["detected_intent"] = analysis.intent.value
            if analysis.requires_human:
                call["handoff_requested"] = True
                call["handoff_reason"] = analysis.transfer_reason

        return analysis

    async def get_call(self, call_id: str) -> dict[str, Any] | None:
        return self.telegram.get_call(call_id)

    async def list_calls(self) -> list[dict[str, Any]]:
        return self.telegram.list_calls()

    async def list_call_events(self, limit: int) -> list[dict[str, Any]]:
        return self.telegram.list_events(limit=limit)

    async def calls_readiness(self) -> dict[str, Any]:
        ready, detail = self.telegram.readiness()
        auth = await self.telegram.auth_status() if ready else {
            "connected": False,
            "authorized": False,
            "detail": detail,
            "session_path": self.settings.telegram_session_path,
        }
        calendar_ready, calendar_detail = self.calendar.readiness()
        return {
            "ready": ready,
            "detail": detail,
            "auth": auth,
            "calendar": {
                "ready": calendar_ready,
                "detail": calendar_detail,
                "cache": self.calendar.cache_snapshot(limit=3),
                "queue": self.calendar.queue_snapshot(limit=5),
            },
            "memory": self.memory.snapshot(),
            "notes": [
                "Telegram bot accounts cannot receive voice calls directly.",
                "Voice calls require authorized Telegram user session (API_ID/API_HASH + sign-in).",
            ],
        }

    async def end_call(self, call_id: str) -> CallEventAck:
        if call_id in self.live_sessions:
            await self.stop_telegram_live_agent(call_id)
        result = await self.telegram.end_call(call_id)
        return CallEventAck(**result)

    async def stream_audio_out(self, call_id: str, payload: CallAudioPlayRequest) -> CallAudioResponse:
        result = await self.telegram.stream_audio_out(call_id, payload.audio_path)
        return CallAudioResponse(**result)

    async def stream_audio_in(self, call_id: str, payload: CallAudioRecordRequest) -> CallAudioResponse:
        result = await self.telegram.stream_audio_in(call_id, payload.output_path)
        return CallAudioResponse(**result)

    async def calendar_cache(self, limit: int = 10) -> CalendarCacheResponse:
        return CalendarCacheResponse(**self.calendar.cache_snapshot(limit=limit))

    async def calendar_queue(self, limit: int = 20) -> CalendarQueueSnapshotResponse:
        return CalendarQueueSnapshotResponse(**self.calendar.queue_snapshot(limit=limit))

    async def calendar_enqueue(self, payload: CalendarQueueRequest) -> CalendarQueueResponse:
        result = await self.calendar.quick_reply_or_enqueue(
            call_id=payload.call_id,
            transcript=payload.transcript,
            context=payload.context,
        )
        return CalendarQueueResponse(
            status=str(result.get("status") or "unknown"),
            detail=str(result.get("detail")) if result.get("detail") is not None else None,
            reply=str(result.get("reply")) if result.get("reply") is not None else None,
            queued=bool(result.get("queued", False)),
            task_id=str(result.get("task_id")) if result.get("task_id") is not None else None,
        )

    async def calendar_process(self, max_items: int = 5) -> CalendarProcessResponse:
        result = await self.calendar.process_queue(max_items=max_items)
        return CalendarProcessResponse(
            status=str(result.get("status") or "unknown"),
            processed=int(result.get("processed") or 0),
            results=result.get("results") or [],
        )

    async def calendar_refresh(self, days: int = 7, max_results: int = 30) -> dict[str, Any]:
        result = await self.calendar.refresh_cache(days=days, max_results=max_results)
        self.memory.set_mid_term_upcoming(self.calendar.cache_snapshot(limit=50).get("events", []))
        self.memory.append_long_term("calendar_refresh", {"days": days, "max_results": max_results})
        return result

    async def start_telegram_live_agent(
        self,
        call_id: str,
        payload: TelegramLiveAgentStartRequest,
    ) -> TelegramLiveAgentResponse:
        call = self.telegram.get_call(call_id)
        if call is None:
            return TelegramLiveAgentResponse(
                call_id=call_id,
                status="not_found",
                detail="Unknown call_id.",
                stt_status="not_started",
                speak_response=payload.speak_response,
            )

        existing = self.live_sessions.get(call_id)
        if existing and existing.get("running"):
            return TelegramLiveAgentResponse(
                call_id=call_id,
                status="already_running",
                detail="Telegram live agent loop is already running for this call.",
                recording_path=existing.get("recording_path"),
                stt_status=str(existing.get("last_stt_status") or "idle"),
                speak_response=bool(existing.get("speak_response", True)),
            )

        recordings_root = Path(self.settings.telegram_audio_root) / "recordings"
        recordings_root.mkdir(parents=True, exist_ok=True)
        recording_path = (recordings_root / f"{call_id}.wav").resolve()

        record_ack = await self.stream_audio_in(
            call_id,
            CallAudioRecordRequest(output_path=str(recording_path)),
        )
        if record_ack.status not in {"recording_in", "ok"}:
            return TelegramLiveAgentResponse(
                call_id=call_id,
                status="record_failed",
                detail=record_ack.detail,
                recording_path=str(recording_path),
                stt_status="not_started",
                speak_response=payload.speak_response,
            )

        session: dict[str, Any] = {
            "call_id": call_id,
            "running": True,
            "recording_path": str(recording_path),
            "context": payload.context,
            "speak_response": payload.speak_response,
            "last_stt_status": "waiting_audio",
            "last_full_transcript": "",
            "last_transcript_delta": "",
            "last_audio_size": 0,
            "pause_until": None,
            "started_at": self._now_iso(),
            "started_monotonic": monotonic(),
            "responses_sent": 0,
            "last_response_at": None,
            "last_processed_snippet": "",
            "loop_ticks": 0,
            "stt_ok_count": 0,
        }
        session["task"] = asyncio.create_task(self._telegram_live_loop(call_id))
        self.live_sessions[call_id] = session

        call["live_agent"] = {
            "running": True,
            "started_at": session["started_at"],
            "recording_path": str(recording_path),
        }

        self.debug.log(
            call_id,
            "live_start",
            {
                "recording_path": str(recording_path),
                "speak_response": payload.speak_response,
                "context": payload.context,
            },
        )

        return TelegramLiveAgentResponse(
            call_id=call_id,
            status="running",
            detail="Telegram live agent loop started.",
            recording_path=str(recording_path),
            stt_status="waiting_audio",
            speak_response=payload.speak_response,
        )

    async def stop_telegram_live_agent(self, call_id: str) -> TelegramLiveAgentResponse:
        session = self.live_sessions.get(call_id)
        if not session:
            return TelegramLiveAgentResponse(
                call_id=call_id,
                status="not_running",
                detail="No Telegram live agent loop is running for this call.",
                speak_response=True,
            )

        session["running"] = False
        task = session.get("task")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        call = self.telegram.get_call(call_id)
        if call is not None:
            live = call.setdefault("live_agent", {})
            live["running"] = False
            live["stopped_at"] = self._now_iso()

        self.live_sessions.pop(call_id, None)
        return TelegramLiveAgentResponse(
            call_id=call_id,
            status="stopped",
            detail="Telegram live agent loop stopped.",
            recording_path=str(session.get("recording_path") or ""),
            stt_status=str(session.get("last_stt_status") or "unknown"),
            speak_response=bool(session.get("speak_response", True)),
        )

    async def telegram_live_agent_status(self, call_id: str) -> TelegramLiveAgentStatusResponse:
        session = self.live_sessions.get(call_id)
        if not session:
            return TelegramLiveAgentStatusResponse(
                call_id=call_id,
                running=False,
                status="not_running",
                detail="No active Telegram live agent loop for this call.",
            )
        responses_sent = int(session.get("responses_sent") or 0)
        detail = f"Telegram live agent loop status fetched. responses_sent={responses_sent}."
        return TelegramLiveAgentStatusResponse(
            call_id=call_id,
            running=bool(session.get("running")),
            status="running" if session.get("running") else "stopped",
            detail=detail,
            recording_path=session.get("recording_path"),
            last_stt_status=session.get("last_stt_status"),
            last_transcript=session.get("last_transcript_delta"),
        )

    async def _telegram_live_loop(self, call_id: str) -> None:
        session = self.live_sessions.get(call_id)
        if session is None:
            return

        poll_seconds = max(0.2, float(self.settings.telegram_live_poll_seconds))
        while True:
            session["loop_ticks"] = int(session.get("loop_ticks") or 0) + 1
            if not session.get("running"):
                self.debug.log(call_id, "loop_stopped", {"reason": "session_not_running"})
                return

            call = self.telegram.get_call(call_id) or {}
            if str(call.get("status", "")).lower() in {"ended", "discarded", "failed"}:
                session["running"] = False
                session["last_stt_status"] = "call_ended"
                self.debug.log(call_id, "loop_stopped", {"reason": "call_ended", "status": call.get("status")})
                return

            pause_until = session.get("pause_until")
            if isinstance(pause_until, datetime) and datetime.now(timezone.utc) < pause_until:
                await asyncio.sleep(0.2)
                continue

            recording_path = Path(str(session["recording_path"]))
            if not recording_path.exists():
                await asyncio.sleep(0.3)
                continue

            file_size = recording_path.stat().st_size
            if session["loop_ticks"] % 15 == 0:
                self.debug.log(
                    call_id,
                    "loop_tick",
                    {
                        "tick": session["loop_ticks"],
                        "file_size": file_size,
                        "last_audio_size": int(session.get("last_audio_size") or 0),
                        "last_stt_status": session.get("last_stt_status"),
                    },
                )
            previous_size = int(session.get("last_audio_size") or 0)
            if file_size < previous_size:
                self.debug.log(
                    call_id,
                    "recording_file_shrunk",
                    {"file_size": file_size, "previous_size": previous_size},
                )
                previous_size = 0
                session["last_audio_size"] = 0
            min_new_bytes = max(256, int(self.settings.stt_min_new_bytes // 2))

            started_monotonic = float(session.get("started_monotonic") or 0.0)
            warmup_elapsed = monotonic() - started_monotonic if started_monotonic else 999.0
            in_warmup = warmup_elapsed < 10.0

            if file_size <= 0:
                await asyncio.sleep(min(0.4, poll_seconds))
                continue
            if (file_size - previous_size) < min_new_bytes and not in_warmup:
                self.debug.log(
                    call_id,
                    "wait_for_more_audio",
                    {
                        "delta_bytes": file_size - previous_size,
                        "min_new_bytes": min_new_bytes,
                        "in_warmup": in_warmup,
                    },
                )
                await asyncio.sleep(min(0.4, poll_seconds))
                continue
            session["last_audio_size"] = file_size

            self.debug.log(
                call_id,
                "stt_transcribe_start",
                {
                    "recording_path": str(recording_path),
                    "file_size": file_size,
                    "tail_seconds": self.settings.stt_tail_seconds,
                    "recent_only": self.settings.stt_recent_only,
                    "timeout_sec": self.settings.stt_transcribe_timeout_seconds,
                },
            )
            stt_started = monotonic()
            text, stt_status = await self.stt.transcribe(str(recording_path))
            self.debug.log(
                call_id,
                "stt_transcribe_done",
                {
                    "status": stt_status,
                    "elapsed_sec": round(monotonic() - stt_started, 3),
                    "chars": len((text or "").strip()),
                },
            )
            session["last_stt_status"] = stt_status
            preview_chars = max(20, int(self.settings.telegram_live_log_transcript_preview_chars))
            if stt_status != "ok":
                # Secondary rescue pass: when recent-only missed, try full file once here too.
                if stt_status == "no_speech":
                    full_text, full_status = await self.stt.transcribe(str(recording_path))
                    if full_status == "ok" and full_text.strip():
                        text = full_text
                        stt_status = "ok"
                        session["last_stt_status"] = stt_status
                    else:
                        self.debug.log(
                            call_id,
                            "stt_not_ok",
                            {
                                "status": stt_status,
                                "chars": len((text or "").strip()),
                                "sample": (text or "")[:preview_chars],
                            },
                        )
                        await asyncio.sleep(poll_seconds)
                        continue
                else:
                    self.debug.log(
                        call_id,
                        "stt_not_ok",
                        {
                            "status": stt_status,
                            "chars": len((text or "").strip()),
                            "sample": (text or "")[:preview_chars],
                        },
                    )
                    await asyncio.sleep(poll_seconds)
                    continue

            session["stt_ok_count"] = int(session.get("stt_ok_count") or 0) + 1
            self.debug.log(
                call_id,
                "stt_ok",
                {
                    "chars": len((text or "").strip()),
                    "sample": (text or "")[:preview_chars],
                    "count": session["stt_ok_count"],
                },
            )

            previous = str(session.get("last_full_transcript") or "")
            delta = self._extract_new_text(previous, text)
            snippet = delta.strip() if delta.strip() else text.strip()
            min_chars = max(3, int(self.settings.stt_min_chars) - 1)
            if len(snippet) < min_chars:
                session["last_full_transcript"] = text
                self.debug.log(call_id, "snippet_too_short", {"chars": len(snippet), "snippet": snippet})
                await asyncio.sleep(poll_seconds)
                continue

            normalized_snippet = " ".join(snippet.split()).strip().lower()
            normalized_last = " ".join(str(session.get("last_processed_snippet") or "").split()).strip().lower()
            if normalized_snippet and normalized_last:
                similarity = SequenceMatcher(None, normalized_snippet, normalized_last).ratio()
                if similarity >= float(self.settings.stt_repeat_similarity_threshold):
                    session["last_full_transcript"] = text
                    self.debug.log(
                        call_id,
                        "snippet_deduped",
                        {
                            "similarity": similarity,
                            "snippet": snippet[:120],
                        },
                    )
                    await asyncio.sleep(poll_seconds)
                    continue

            session["last_full_transcript"] = text
            session["last_transcript_delta"] = snippet

            try:
                context = dict(session.get("context") or {})
                context["source"] = "telegram_live_loop"
                context["stt_provider"] = self.settings.stt_provider
                status_before = str(call.get("status") or "").lower()
                if status_before in {"ended", "discarded", "failed"}:
                    self.debug.log(call_id, "skip_live_respond_call_not_active", {"status": status_before})
                    await asyncio.sleep(poll_seconds)
                    continue
                started = monotonic()
                response = await self.live_agent_respond(
                    call_id=call_id,
                    transcript=snippet,
                    context=context,
                    speak_response=bool(session.get("speak_response", True)),
                )
                self.debug.log(
                    call_id,
                    "live_respond_ok",
                    {
                        "elapsed_sec": round(monotonic() - started, 3),
                        "reply_chars": len((response.reply or "").strip()),
                        "call_audio_status": response.call_audio_status,
                    },
                )
                if str((response.call_audio_status or "").lower()) == "error":
                    self.debug.log(
                        call_id,
                        "audio_out_error_after_response",
                        {
                            "reply": (response.reply or "")[:140],
                            "tts_status": response.tts_status,
                            "call_audio_status": response.call_audio_status,
                            "call_status": call.get("status"),
                        },
                    )

                session["last_processed_snippet"] = snippet
                session["responses_sent"] = int(session.get("responses_sent") or 0) + 1
                session["last_response_at"] = self._now_iso()
                self.telegram._append_event(  # type: ignore[attr-defined]
                    call_id,
                    "live_turn",
                    {
                        "delta_chars": len(snippet),
                        "reply_chars": len((response.reply or "").strip()),
                        "tts_status": response.tts_status,
                        "call_audio_status": response.call_audio_status,
                        "responses_sent": session["responses_sent"],
                    },
                )
                if str(response.call_audio_status or "") != "streaming_out":
                    self.telegram._append_event(  # type: ignore[attr-defined]
                        call_id,
                        "live_turn_audio_not_streaming",
                        {
                            "tts_status": response.tts_status,
                            "call_audio_status": response.call_audio_status,
                        },
                    )
            except Exception as exc:
                session["last_stt_status"] = "agent_error"
                self.debug.log(
                    call_id,
                    "live_turn_error",
                    {
                        "error": exc.__class__.__name__,
                        "detail": str(exc),
                        "call_status": call.get("status"),
                        "responses_sent": session.get("responses_sent"),
                    },
                )
                self.telegram._append_event(  # type: ignore[attr-defined]
                    call_id,
                    "live_turn_error",
                    {"error": exc.__class__.__name__, "detail": str(exc)},
                )

            await asyncio.sleep(poll_seconds)

    async def _stop_all_live_sessions(self) -> None:
        call_ids = list(self.live_sessions.keys())
        for call_id in call_ids:
            try:
                await self.stop_telegram_live_agent(call_id)
            except Exception:
                continue

    async def _stop_auto_live_task(self) -> None:
        task = self._auto_live_task
        self._auto_live_task = None
        if not task:
            return
        if task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _stop_calendar_worker_task(self) -> None:
        task = self._calendar_worker_task
        self._calendar_worker_task = None
        if not task:
            return
        if task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _auto_attach_live_loop(self) -> None:
        scan_seconds = max(0.5, float(self.settings.telegram_auto_start_scan_seconds))
        retry_seconds = max(4.0, scan_seconds * 2.0)

        while True:
            try:
                now = datetime.now(timezone.utc)
                calls = self.telegram.list_calls()
                for call in calls:
                    call_id = str(call.get("call_id") or "").strip()
                    if not call_id:
                        continue
                    status = str(call.get("status") or "").strip().lower()
                    if status != "active":
                        continue

                    should_greet = (
                        bool(self.settings.assistant_auto_greet_on_connect)
                        and not bool(call.get("greeting_sent"))
                    )
                    if should_greet:
                        greeting = await self._play_greeting_with_retry(call_id, source="auto_attach")
                        if greeting.get("status") == "streaming_out":
                            call["greeting_sent"] = True

                    existing = self.live_sessions.get(call_id)
                    if existing and existing.get("running"):
                        continue

                    live_meta = call.setdefault("live_agent", {})
                    next_retry_at = live_meta.get("next_retry_at")
                    parsed_next_retry = self._parse_iso(next_retry_at) if isinstance(next_retry_at, str) else None
                    if parsed_next_retry and parsed_next_retry > now:
                        continue

                    result = await self.start_telegram_live_agent(
                        call_id,
                        TelegramLiveAgentStartRequest(
                            context={"source": "auto_attach_watcher"},
                            speak_response=self.settings.telegram_auto_start_live_speak_response,
                        ),
                    )
                    live_meta["auto_last_status"] = result.status
                    live_meta["auto_last_detail"] = result.detail
                    live_meta["auto_last_attempt_at"] = self._now_iso()
                    if result.status not in {"running", "already_running"}:
                        live_meta["next_retry_at"] = (now + timedelta(seconds=retry_seconds)).isoformat()
                    else:
                        live_meta.pop("next_retry_at", None)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

            await asyncio.sleep(scan_seconds)

    async def _calendar_worker_loop(self) -> None:
        poll_seconds = max(0.5, float(self.settings.calendar_worker_poll_seconds))
        batch_size = max(1, int(self.settings.calendar_worker_batch_size))

        while True:
            try:
                await self.calendar.process_queue(max_items=batch_size)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(poll_seconds)

    async def _handle_reminder_flow(
        self,
        call_id: str,
        transcript: str,
        speak_response: bool,
    ) -> AgentLiveRespondResponse:
        normalized = " ".join((transcript or "").split()).strip().lower()
        fingerprint = hashlib.sha1(normalized.encode("utf-8", "ignore")).hexdigest()[:16]
        existing = self._reminder_flow_state.get(call_id, {})

        if existing.get("awaiting_result") and existing.get("fingerprint") == fingerprint:
            reply = "I’m still checking your availability. One moment please."
            return await self._fast_fallback_response(
                call_id=call_id,
                snippet=transcript,
                reply=reply,
                action_item="reminder_flow_waiting",
                speak_response=speak_response,
            )

        # Step 1: immediate pre-recorded acknowledgment
        ack_reply = "Let me check your availability for that reminder."
        ack = await self._fast_fallback_response(
            call_id=call_id,
            snippet=transcript,
            reply=ack_reply,
            action_item="reminder_flow_ack",
            speak_response=speak_response,
        )

        self._reminder_flow_state[call_id] = {
            "awaiting_result": True,
            "fingerprint": fingerprint,
            "requested_at": self._now_iso(),
        }

        # Step 2: fast availability decision using cached schedule + optional planner queue
        snapshot = self.calendar.cache_snapshot(limit=8)
        events = snapshot.get("events", []) if isinstance(snapshot, dict) else []
        busy_count = len(events)

        queued = await self.calendar.quick_reply_or_enqueue(
            call_id=call_id,
            transcript=transcript,
            context={"source": "reminder_flow"},
        )
        queued_id = queued.get("task_id") if isinstance(queued, dict) else None

        # Heuristic decision phrase (pre-recorded family)
        if busy_count >= 5:
            result_reply = "You’re not very available. I can still queue this reminder around your schedule."
        elif busy_count >= 1:
            result_reply = "You have some events, but yes, I can place this reminder."
        else:
            result_reply = "Yes, you’re available. I can set this reminder now."

        # Prime template cache for repeated flows
        if "reminder_result_available" not in self._template_audio_cache:
            path, _ = await self.tts.synthesize("Yes, you’re available. I can set this reminder now.", call_id="template-reminder_result_available")
            if path:
                self._template_audio_cache["reminder_result_available"] = path
        if "reminder_result_busy" not in self._template_audio_cache:
            path, _ = await self.tts.synthesize("You’re not very available. I can still queue this reminder around your schedule.", call_id="template-reminder_result_busy")
            if path:
                self._template_audio_cache["reminder_result_busy"] = path

        result = await self._fast_fallback_response(
            call_id=call_id,
            snippet=transcript,
            reply=result_reply,
            action_item="reminder_flow_result",
            speak_response=speak_response,
        )

        # Adaptive template augmentation for likely follow-up asks.
        await self._update_predictive_templates(
            call_id=call_id,
            trigger_text=transcript,
            busy_count=busy_count,
        )

        result.action_items = list(result.action_items) + [f"calendar_checked:{busy_count}"]
        if queued_id:
            result.action_items.append(f"calendar_queue:{queued_id}")
        result.action_items = result.action_items[:8]

        self._reminder_flow_state[call_id] = {
            "awaiting_result": False,
            "fingerprint": fingerprint,
            "last_result": result_reply,
            "completed_at": self._now_iso(),
            "busy_count": busy_count,
        }

        self.memory.append_long_term(
            "reminder_flow",
            {
                "call_id": call_id,
                "transcript": transcript,
                "busy_count": busy_count,
                "queued_id": queued_id,
                "result_reply": result_reply,
            },
        )

        return result

    async def _update_predictive_templates(self, call_id: str, trigger_text: str, busy_count: int) -> None:
        try:
            path = Path(self.settings.agent_live_template_path)
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return

            if busy_count >= 4:
                dynamic_reply = "You are busy around that time. I can suggest the next available slot."
            elif busy_count >= 1:
                dynamic_reply = "You have some events, but I can fit this reminder in."
            else:
                dynamic_reply = "You are available, so I can set this reminder now."

            dynamic_item = {
                "id": "predictive_reminder_followup",
                "keywords": ["is that possible", "am i available", "can i do that", "do i have time"],
                "reply": dynamic_reply,
                "priority": 13,
                "calendar_check": True,
            }

            replaced = False
            for idx, item in enumerate(data):
                if str(item.get("id")) == "predictive_reminder_followup":
                    data[idx] = dynamic_item
                    replaced = True
                    break
            if not replaced:
                data.append(dynamic_item)

            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.template_matcher = LiveTemplateMatcher(self.settings)
            self.memory.append_long_term(
                "predictive_template_update",
                {
                    "call_id": call_id,
                    "trigger_text": trigger_text,
                    "busy_count": busy_count,
                    "template_id": "predictive_reminder_followup",
                },
            )
        except Exception as exc:
            self.debug.log(call_id, "predictive_template_update_failed", {"error": exc.__class__.__name__, "detail": str(exc)})

    async def _fast_fallback_response(
        self,
        call_id: str,
        snippet: str,
        reply: str,
        action_item: str,
        speak_response: bool,
    ) -> AgentLiveRespondResponse:
        tts_audio_path: str | None = None
        tts_status: str | None = None
        call_audio_status: str | None = None

        if speak_response:
            tts_audio_path, tts_status = await self.tts.synthesize(reply, call_id=call_id)
            self.debug.log(
                call_id,
                "fallback_tts",
                {"tts_status": tts_status, "has_audio": bool(tts_audio_path), "reply": reply[:120]},
            )
            if tts_audio_path:
                stream_result = await self.telegram.stream_audio_out(call_id, tts_audio_path)
                call_audio_status = str(stream_result.get("status"))
                self.debug.log(
                    call_id,
                    "fallback_audio_out",
                    {"audio_path": tts_audio_path, "status": call_audio_status, "detail": stream_result.get("detail")},
                )
            else:
                call_audio_status = "not_streamed"

        return AgentLiveRespondResponse(
            call_id=call_id,
            transcript=snippet,
            reply=reply,
            intent=AgentAnalyzeResponse(call_id=call_id, reply=reply, model=self.settings.zai_model).intent,
            confidence=0.2,
            requires_human=False,
            transfer_reason=None,
            action_items=[action_item],
            extracted_fields={},
            model=self.settings.zai_model,
            tts_audio_path=tts_audio_path,
            tts_status=tts_status,
            call_audio_status=call_audio_status,
        )

    @staticmethod
    def _is_low_quality_snippet(text: str) -> bool:
        normalized = " ".join((text or "").split()).strip()
        if len(normalized) < 4:
            return True
        words = [w for w in re.split(r"\s+", normalized) if w]
        if len(words) < 2:
            return True
        if len(set(w.lower() for w in words)) <= 1 and len(words) >= 3:
            return True
        alpha_chars = sum(ch.isalpha() for ch in normalized)
        return alpha_chars < max(3, int(len(normalized) * 0.45))

    async def _play_greeting_with_retry(self, call_id: str, source: str) -> dict[str, Any]:
        tts_audio_path, tts_status = await self.tts.synthesize(
            self.settings.assistant_greeting_message,
            call_id=call_id,
        )
        if not tts_audio_path:
            self.telegram._append_event(  # type: ignore[attr-defined]
                call_id,
                "greeting_tts_failed",
                {"source": source, "tts_status": tts_status},
            )
            return {"status": "tts_failed", "detail": str(tts_status or "unknown")}

        attempts = 3
        delays = [0.0, 0.7, 1.4]
        last_status = "unknown"
        last_detail = "no detail"
        ffmpeg_missing = False
        for i in range(attempts):
            if delays[i] > 0:
                await asyncio.sleep(delays[i])
            stream_result = await self.telegram.stream_audio_out(call_id, tts_audio_path)
            last_status = str(stream_result.get("status") or "unknown")
            last_detail = str(stream_result.get("detail") or "no detail")
            self.telegram._append_event(  # type: ignore[attr-defined]
                call_id,
                "greeting_stream_attempt",
                {
                    "source": source,
                    "attempt": i + 1,
                    "status": last_status,
                    "detail": last_detail,
                    "audio_path": tts_audio_path,
                },
            )
            if last_status == "streaming_out":
                return {"status": last_status, "detail": last_detail}

            if "ffmpeg" in last_detail.lower() and "not found" in last_detail.lower():
                ffmpeg_missing = True
                break

        if ffmpeg_missing:
            self.telegram._append_event(  # type: ignore[attr-defined]
                call_id,
                "greeting_stream_aborted",
                {
                    "source": source,
                    "reason": "ffmpeg_missing",
                    "detail": last_detail,
                    "audio_path": tts_audio_path,
                },
            )

        return {"status": last_status, "detail": last_detail}

    @staticmethod
    def _extract_new_text(previous: str, current: str) -> str:
        prev = " ".join((previous or "").split()).strip()
        cur = " ".join((current or "").split()).strip()
        if not cur:
            return ""
        if not prev:
            return cur
        if cur.startswith(prev):
            return cur[len(prev) :].strip()

        overlap = 0
        max_check = min(len(prev), len(cur))
        for size in range(max_check, 0, -1):
            if prev.endswith(cur[:size]):
                overlap = size
                break
        return cur[overlap:].strip()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_iso(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value)
        except Exception:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    async def _zai_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.zai_api_key:
            return {"error": "Missing ZAI_API_KEY in environment."}

        base_url = self.settings.zai_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.zai_api_key}",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.zai_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 300:
                return {
                    "error": f"GLM request failed ({response.status_code}).",
                    "raw": response.text[:240],
                }
            return {"data": response.json()}
        except Exception as exc:
            return {"error": f"Connection error: {exc.__class__.__name__}"}

    @staticmethod
    def _extract_message(data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices") or []
        if not choices:
            return {}
        msg = choices[0].get("message") or {}
        if not isinstance(msg, dict):
            return {}
        return msg
