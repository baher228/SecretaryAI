import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import (
    AgentLiveRespondResponse,
    AgentAnalyzeResponse,
    AgentReplyResponse,
    ArchitectureOverview,
    CallAudioPlayRequest,
    CallAudioRecordRequest,
    CallAudioResponse,
    CallEventAck,
    CallTranscriptRequest,
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
from secretary_ai.services.stt import STTEngine
from secretary_ai.services.telegram_calls import TelegramCallService
from secretary_ai.services.tts import TTSEngine


class SecretaryService:
    """Main orchestrator: Z.AI reasoning + Telegram MTProto call provider."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.telegram = TelegramCallService(settings)
        self.ai = SecretaryAIAgent(settings)
        self.tts = TTSEngine(settings)
        self.stt = STTEngine(settings)
        self.live_sessions: dict[str, dict[str, Any]] = {}
        self._auto_live_task: asyncio.Task | None = None

    async def startup(self) -> None:
        await self.telegram.start()
        if self.settings.telegram_auto_start_live_agent:
            self._auto_live_task = asyncio.create_task(self._auto_attach_live_loop())

    async def shutdown(self) -> None:
        await self._stop_auto_live_task()
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
            tts_audio_path, tts_status = await self.tts.synthesize(
                self.settings.assistant_greeting_message,
                call_id=response.call_id,
            )
            if tts_audio_path:
                stream_result = await self.telegram.stream_audio_out(response.call_id, tts_audio_path)
                stream_status = str(stream_result.get("status"))
                response.detail = f"{response.detail} Greeting: {stream_status}."
            else:
                response.detail = f"{response.detail} Greeting TTS: {tts_status}."

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
        analysis = await self.analyze_agent_turn(call_id=call_id, transcript=transcript, context=context)

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
                    cooldown = max(0.5, float(self.settings.telegram_live_tts_cooldown_seconds))
                    session["pause_until"] = datetime.now(timezone.utc) + timedelta(seconds=cooldown)
                    session["last_call_audio_status"] = call_audio_status

        return AgentLiveRespondResponse(
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

    async def analyze_agent_turn(
        self,
        call_id: str,
        transcript: str,
        context: dict[str, Any],
    ) -> AgentAnalyzeResponse:
        self.telegram.append_transcript(call_id, transcript, metadata=context)
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
            "pause_until": None,
            "started_at": self._now_iso(),
        }
        session["task"] = asyncio.create_task(self._telegram_live_loop(call_id))
        self.live_sessions[call_id] = session

        call["live_agent"] = {
            "running": True,
            "started_at": session["started_at"],
            "recording_path": str(recording_path),
        }

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
        return TelegramLiveAgentStatusResponse(
            call_id=call_id,
            running=bool(session.get("running")),
            status="running" if session.get("running") else "stopped",
            detail="Telegram live agent loop status fetched.",
            recording_path=session.get("recording_path"),
            last_stt_status=session.get("last_stt_status"),
            last_transcript=session.get("last_transcript_delta"),
        )

    async def _telegram_live_loop(self, call_id: str) -> None:
        session = self.live_sessions.get(call_id)
        if session is None:
            return

        poll_seconds = max(1.0, float(self.settings.telegram_live_poll_seconds))
        while True:
            if not session.get("running"):
                return

            call = self.telegram.get_call(call_id) or {}
            if str(call.get("status", "")).lower() in {"ended", "discarded", "failed"}:
                session["running"] = False
                session["last_stt_status"] = "call_ended"
                return

            pause_until = session.get("pause_until")
            if isinstance(pause_until, datetime) and datetime.now(timezone.utc) < pause_until:
                await asyncio.sleep(0.4)
                continue

            text, stt_status = await self.stt.transcribe(str(session["recording_path"]))
            session["last_stt_status"] = stt_status

            if stt_status != "ok":
                await asyncio.sleep(poll_seconds)
                continue

            previous = str(session.get("last_full_transcript") or "")
            delta = self._extract_new_text(previous, text)
            if len(delta.strip()) < int(self.settings.stt_min_chars):
                await asyncio.sleep(poll_seconds)
                continue

            session["last_full_transcript"] = text
            session["last_transcript_delta"] = delta
            context = dict(session.get("context") or {})
            context["source"] = "telegram_live_loop"
            context["stt_provider"] = self.settings.stt_provider

            try:
                await self.live_agent_respond(
                    call_id=call_id,
                    transcript=delta,
                    context=context,
                    speak_response=bool(session.get("speak_response", True)),
                )
            except Exception:
                session["last_stt_status"] = "agent_error"

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

    async def _auto_attach_live_loop(self) -> None:
        scan_seconds = max(1.0, float(self.settings.telegram_auto_start_scan_seconds))
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
