import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from secretary_ai.core.config import Settings

try:
    from pytgcalls import PyTgCalls, filters
    from pytgcalls.types import ChatUpdate, StreamEnded, StreamFrames
except Exception:  # pragma: no cover - import failure is surfaced in readiness checks
    PyTgCalls = None  # type: ignore[assignment]
    filters = None  # type: ignore[assignment]
    ChatUpdate = None  # type: ignore[assignment]
    StreamEnded = None  # type: ignore[assignment]
    StreamFrames = None  # type: ignore[assignment]

try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except Exception:  # pragma: no cover - import failure is surfaced in readiness checks
    TelegramClient = None  # type: ignore[assignment]
    SessionPasswordNeededError = Exception  # type: ignore[assignment]


class TelegramCallService:
    """Telegram MTProto user-account calling adapter for MVP/hackathon use."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        self._calls = None
        self._handlers_registered = False
        self._started = False
        self._lock = asyncio.Lock()

        self.calls: dict[str, dict[str, Any]] = {}
        self.call_events: list[dict[str, Any]] = []
        self.pending_phone_hashes: dict[str, str] = {}

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return
            if not self._library_ready():
                return
            if not self._credentials_ready():
                return
            await self._ensure_connected()
            if await self._client.is_user_authorized():
                await self._ensure_calls_started()
            self._started = True

    async def stop(self) -> None:
        async with self._lock:
            if self._calls is not None:
                try:
                    await self._calls.stop()
                except Exception:
                    pass
            self._calls = None
            self._handlers_registered = False
            if self._client is not None:
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
            self._client = None
            self._started = False

    def readiness(self) -> tuple[bool, str]:
        if not self._library_ready():
            return (
                False,
                "Missing dependencies. Install telethon and py-tgcalls in this environment.",
            )
        if not self._credentials_ready():
            return (
                False,
                "Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in environment.",
            )
        return True, "Telegram MTProto dependencies and credentials are available."

    async def auth_status(self) -> dict[str, Any]:
        ready, detail = self.readiness()
        if not ready:
            return {
                "connected": False,
                "authorized": False,
                "detail": detail,
                "session_path": self.settings.telegram_session_path,
            }
        await self._ensure_connected()
        assert self._client is not None
        authorized = await self._client.is_user_authorized()
        return {
            "connected": bool(self._client.is_connected()),
            "authorized": bool(authorized),
            "detail": (
                "Authorized Telegram user session is active."
                if authorized
                else "Session not authorized yet. Send code and sign in."
            ),
            "session_path": self.settings.telegram_session_path,
        }

    async def send_code(self, phone_number: str) -> dict[str, Any]:
        ready, detail = self.readiness()
        if not ready:
            return {
                "status": "not_ready",
                "phone_number": phone_number,
                "phone_code_hash": None,
                "detail": detail,
            }

        await self._ensure_connected()
        assert self._client is not None
        result = await self._client.send_code_request(phone_number)
        code_hash = result.phone_code_hash
        self.pending_phone_hashes[phone_number] = code_hash
        return {
            "status": "code_sent",
            "phone_number": phone_number,
            "phone_code_hash": code_hash,
            "detail": "Code sent to Telegram app/SMS for this number.",
        }

    async def sign_in(
        self,
        phone_number: str,
        code: str | None,
        phone_code_hash: str | None,
        password: str | None,
    ) -> dict[str, Any]:
        ready, detail = self.readiness()
        if not ready:
            return {"status": "not_ready", "authorized": False, "detail": detail}

        await self._ensure_connected()
        assert self._client is not None

        try:
            if password and not code:
                await self._client.sign_in(password=password)
            else:
                selected_hash = phone_code_hash or self.pending_phone_hashes.get(phone_number)
                if not selected_hash:
                    return {
                        "status": "missing_code_hash",
                        "authorized": False,
                        "detail": "Missing phone_code_hash. Call send-code first or pass hash explicitly.",
                    }
                if not code:
                    return {
                        "status": "missing_code",
                        "authorized": False,
                        "detail": "Missing verification code.",
                    }
                await self._client.sign_in(
                    phone=phone_number,
                    code=code,
                    phone_code_hash=selected_hash,
                )
        except SessionPasswordNeededError:
            return {
                "status": "password_required",
                "authorized": False,
                "detail": "2FA password is required. Retry sign-in with password.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "authorized": False,
                "detail": f"Sign-in failed: {exc.__class__.__name__}",
            }

        if await self._client.is_user_authorized():
            await self._ensure_calls_started()
            self.pending_phone_hashes.pop(phone_number, None)
            return {
                "status": "authorized",
                "authorized": True,
                "detail": "Telegram user session authorized.",
            }
        return {"status": "unknown", "authorized": False, "detail": "Authorization did not complete."}

    async def start_outbound_call(
        self,
        target_user: str,
        purpose: str,
        initial_audio_path: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not await self._can_place_calls():
            return {
                "call_id": "",
                "status": "not_authorized",
                "detail": "Telegram user is not authorized. Complete /telegram/auth flow first.",
                "provider": "telegram_mtproto",
                "chat_id": None,
            }

        chat_id = await self._resolve_chat_id(target_user)
        if not chat_id:
            return {
                "call_id": "",
                "status": "invalid_target",
                "detail": f"Could not resolve target user: {target_user}",
                "provider": "telegram_mtproto",
                "chat_id": None,
            }

        call_id = self._call_id(chat_id)
        self._upsert_call(
            call_id,
            {
                "call_id": call_id,
                "chat_id": chat_id,
                "target_user": target_user,
                "direction": "outbound",
                "purpose": purpose,
                "status": "dialing",
                "metadata": metadata,
                "updated_at": self._now_iso(),
            },
        )
        self._append_event(call_id, "outbound_request", {"target_user": target_user, "purpose": purpose})

        try:
            assert self._calls is not None
            source_path = self._normalize_optional_audio_path(initial_audio_path)
            if source_path:
                await self._calls.play(chat_id, stream=source_path)
            else:
                await self._calls.play(chat_id)
            self._upsert_call(
                call_id,
                {"status": "active", "connected_at": self._now_iso(), "updated_at": self._now_iso()},
            )
            self._append_event(call_id, "call_connected", {"chat_id": chat_id})
            return {
                "call_id": call_id,
                "status": "active",
                "detail": "Outbound Telegram private call started.",
                "provider": "telegram_mtproto",
                "chat_id": chat_id,
            }
        except Exception as exc:
            self._upsert_call(call_id, {"status": "failed", "updated_at": self._now_iso()})
            self._append_event(call_id, "call_failed", {"error": exc.__class__.__name__})
            return {
                "call_id": call_id,
                "status": "failed",
                "detail": f"Outbound call failed: {exc.__class__.__name__}",
                "provider": "telegram_mtproto",
                "chat_id": chat_id,
            }

    async def end_call(self, call_id: str) -> dict[str, Any]:
        call = self.calls.get(call_id)
        if not call:
            return {"status": "not_found", "detail": "Unknown call_id."}
        if not await self._can_place_calls():
            return {"status": "not_authorized", "detail": "Telegram calls client is not ready."}

        try:
            assert self._calls is not None
            await self._calls.leave_call(call["chat_id"])
            self._upsert_call(call_id, {"status": "ended", "updated_at": self._now_iso()})
            self._append_event(call_id, "call_ended", {})
            return {"status": "ended", "detail": "Call ended."}
        except Exception as exc:
            return {"status": "error", "detail": f"Could not end call: {exc.__class__.__name__}"}

    async def stream_audio_out(self, call_id: str, audio_path: str) -> dict[str, Any]:
        call = self.calls.get(call_id)
        if not call:
            return {"call_id": call_id, "status": "not_found", "detail": "Unknown call_id."}
        if not await self._can_place_calls():
            return {
                "call_id": call_id,
                "status": "not_authorized",
                "detail": "Telegram calls client is not ready.",
            }

        normalized = self._normalize_audio_path(audio_path)
        if not normalized.exists():
            return {
                "call_id": call_id,
                "status": "missing_file",
                "detail": f"Audio file does not exist: {normalized}",
            }

        try:
            assert self._calls is not None
            await self._calls.play(call["chat_id"], stream=str(normalized))
            self._append_event(call_id, "audio_out_started", {"audio_path": str(normalized)})
            return {
                "call_id": call_id,
                "status": "streaming_out",
                "detail": "Audio file is being streamed into the call.",
            }
        except Exception as exc:
            return {
                "call_id": call_id,
                "status": "error",
                "detail": f"Could not stream outgoing audio: {exc.__class__.__name__}",
            }

    async def stream_audio_in(self, call_id: str, output_path: str) -> dict[str, Any]:
        call = self.calls.get(call_id)
        if not call:
            return {"call_id": call_id, "status": "not_found", "detail": "Unknown call_id."}
        if not await self._can_place_calls():
            return {
                "call_id": call_id,
                "status": "not_authorized",
                "detail": "Telegram calls client is not ready.",
            }

        normalized = self._normalize_audio_path(output_path)
        normalized.parent.mkdir(parents=True, exist_ok=True)

        try:
            assert self._calls is not None
            await self._calls.record(call["chat_id"], stream=str(normalized))
            self._append_event(call_id, "audio_in_recording", {"output_path": str(normalized)})
            return {
                "call_id": call_id,
                "status": "recording_in",
                "detail": "Incoming call audio recording started.",
            }
        except Exception as exc:
            return {
                "call_id": call_id,
                "status": "error",
                "detail": f"Could not start recording: {exc.__class__.__name__}",
            }

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        return self.calls.get(call_id)

    def list_calls(self) -> list[dict[str, Any]]:
        return sorted(self.calls.values(), key=lambda call: call.get("updated_at", ""), reverse=True)

    def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.call_events[-limit:]

    def append_transcript(
        self,
        call_id: str,
        transcript: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        call = self.calls.get(call_id)
        if not call:
            call = {
                "call_id": call_id,
                "status": "transcript_only",
                "direction": "inbound",
                "updated_at": self._now_iso(),
            }
            self.calls[call_id] = call

        transcripts = call.setdefault("transcripts", [])
        entry = {
            "text": transcript,
            "metadata": metadata or {},
            "timestamp": self._now_iso(),
        }
        transcripts.append(entry)
        self._upsert_call(call_id, {"updated_at": self._now_iso()})
        self._append_event(call_id, "transcript_received", {"chars": len(transcript)})
        return call

    async def _ensure_connected(self) -> None:
        if self._client is not None and self._client.is_connected():
            return
        if TelegramClient is None:
            return
        session_path = Path(self.settings.telegram_session_path)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = TelegramClient(
            str(session_path),
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )
        await self._client.connect()

    async def _ensure_calls_started(self) -> None:
        if self._calls is not None:
            return
        if PyTgCalls is None or self._client is None:
            return
        self._calls = PyTgCalls(self._client)
        self._register_handlers()
        await self._calls.start()

    def _register_handlers(self) -> None:
        if self._handlers_registered or self._calls is None or filters is None or ChatUpdate is None:
            return

        watched_chat_states = (
            ChatUpdate.Status.INCOMING_CALL
            | ChatUpdate.Status.DISCARDED_CALL
            | ChatUpdate.Status.BUSY_CALL
            | ChatUpdate.Status.LEFT_CALL
        )

        @self._calls.on_update(filters.chat_update(watched_chat_states))
        async def _on_chat_update(_, update: Any) -> None:
            await self._handle_chat_update(update)

        if StreamEnded is not None:

            @self._calls.on_update(filters.stream_end())
            async def _on_stream_end(_, update: Any) -> None:
                await self._handle_stream_end(update)

        if StreamFrames is not None:

            @self._calls.on_update(filters.stream_frame())
            async def _on_stream_frame(_, update: Any) -> None:
                await self._handle_stream_frames(update)

        self._handlers_registered = True

    async def _handle_chat_update(self, update: Any) -> None:
        chat_id = int(update.chat_id)
        call_id = self._call_id(chat_id)
        status = "updated"
        event = "chat_update"

        if update.status & ChatUpdate.Status.INCOMING_CALL:
            status = "ringing"
            event = "incoming_call"
        if update.status & ChatUpdate.Status.BUSY_CALL:
            status = "busy"
            event = "busy_call"
        if update.status & ChatUpdate.Status.DISCARDED_CALL:
            status = "discarded"
            event = "discarded_call"
        if update.status & ChatUpdate.Status.LEFT_CALL:
            status = "ended"
            event = "left_call"

        self._upsert_call(
            call_id,
            {
                "call_id": call_id,
                "chat_id": chat_id,
                "direction": "inbound",
                "status": status,
                "updated_at": self._now_iso(),
            },
        )
        self._append_event(call_id, event, {"status": str(update.status)})

        should_auto_answer = (
            bool(self.settings.telegram_auto_answer_inbound)
            and update.status & ChatUpdate.Status.INCOMING_CALL
            and self._calls is not None
        )
        if should_auto_answer:
            try:
                await self._calls.play(chat_id)
                self._upsert_call(call_id, {"status": "active", "updated_at": self._now_iso()})
                self._append_event(call_id, "auto_answered", {})
            except Exception as exc:
                self._append_event(call_id, "auto_answer_failed", {"error": exc.__class__.__name__})

    async def _handle_stream_end(self, update: Any) -> None:
        call_id = self._call_id(int(update.chat_id))
        self._append_event(
            call_id,
            "stream_end",
            {
                "stream_type": str(getattr(update, "stream_type", "")),
                "device": str(getattr(update, "device", "")),
            },
        )
        self._upsert_call(call_id, {"updated_at": self._now_iso()})

    async def _handle_stream_frames(self, update: Any) -> None:
        call_id = self._call_id(int(update.chat_id))
        frames = getattr(update, "frames", []) or []
        total_bytes = 0
        for frame in frames:
            payload = getattr(frame, "data", b"")
            if isinstance(payload, (bytes, bytearray)):
                total_bytes += len(payload)
        metrics = self.calls.setdefault(call_id, {}).setdefault("stream_metrics", {})
        metrics["frame_batches"] = int(metrics.get("frame_batches", 0)) + 1
        metrics["bytes_seen"] = int(metrics.get("bytes_seen", 0)) + total_bytes
        self.calls[call_id]["updated_at"] = self._now_iso()

    async def _can_place_calls(self) -> bool:
        ready, _ = self.readiness()
        if not ready:
            return False
        await self._ensure_connected()
        assert self._client is not None
        if not await self._client.is_user_authorized():
            return False
        await self._ensure_calls_started()
        return self._calls is not None

    async def _resolve_chat_id(self, target_user: str) -> int | None:
        if self._client is None:
            return None
        try:
            entity = await self._client.get_entity(target_user)
            return int(entity.id)
        except Exception:
            try:
                return int(target_user)
            except ValueError:
                return None

    def _upsert_call(self, call_id: str, updates: dict[str, Any]) -> None:
        existing = self.calls.get(call_id, {})
        self.calls[call_id] = {**existing, **updates}

    def _append_event(self, call_id: str, event_type: str, payload: dict[str, Any]) -> None:
        evt = {
            "call_id": call_id,
            "type": event_type,
            "payload": payload,
            "timestamp": self._now_iso(),
        }
        self.call_events.append(evt)
        if len(self.call_events) > 2000:
            self.call_events = self.call_events[-1000:]

    def _normalize_optional_audio_path(self, audio_path: str | None) -> str | None:
        if not audio_path:
            return None
        normalized = self._normalize_audio_path(audio_path)
        if not normalized.exists():
            return None
        return str(normalized)

    def _normalize_audio_path(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        root = Path(self.settings.telegram_audio_root)
        root.mkdir(parents=True, exist_ok=True)
        return root / candidate

    def _library_ready(self) -> bool:
        return TelegramClient is not None and PyTgCalls is not None

    def _credentials_ready(self) -> bool:
        return bool(self.settings.telegram_api_id and self.settings.telegram_api_hash)

    @staticmethod
    def _call_id(chat_id: int) -> str:
        return f"tg-{chat_id}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
