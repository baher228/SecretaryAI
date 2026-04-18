from fastapi.testclient import TestClient

from secretary_ai.core.config import get_settings
from secretary_ai.domain.models import (
    AgentAnalyzeResponse,
    AgentLiveRespondResponse,
    AgentReplyResponse,
    ModelCheckResponse,
    OutboundCallResponse,
    TelegramLiveAgentResponse,
    TelegramLiveAgentStatusResponse,
    TelegramAuthStatusResponse,
)
from secretary_ai.main import create_app
from secretary_ai.services.secretary import SecretaryService


def test_health_reports_telegram_mvp_mode() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "telegram_mtproto_mvp"


def test_architecture_mentions_telegram_components() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/architecture")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "telegram_mtproto_mvp"
    assert "Telegram Calls Engine (py-tgcalls private calls)" in payload["components"]


def test_dashboard_endpoint_exists() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Secretary AI Control Center" in response.text


def test_model_check_route_works_with_mock(monkeypatch) -> None:
    async def fake_check_model_connection(self, prompt: str) -> ModelCheckResponse:
        return ModelCheckResponse(
            provider="z.ai",
            model="glm-5.1",
            connected=True,
            detail="mocked",
            output=f"echo:{prompt}",
        )

    monkeypatch.setattr(SecretaryService, "check_model_connection", fake_check_model_connection)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/model/check", json={"prompt": "Say hello"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "z.ai"
    assert payload["connected"] is True
    assert payload["output"] == "echo:Say hello"


def test_telegram_auth_status_route_works_with_mock(monkeypatch) -> None:
    async def fake_auth_status(self) -> TelegramAuthStatusResponse:
        return TelegramAuthStatusResponse(
            connected=True,
            authorized=True,
            detail="mocked",
            session_path=".telegram/secretary",
        )

    monkeypatch.setattr(SecretaryService, "telegram_auth_status", fake_auth_status)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/telegram/auth/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["authorized"] is True
    assert payload["connected"] is True


def test_outbound_call_route_works_with_mock(monkeypatch) -> None:
    async def fake_start_outbound_call(self, payload) -> OutboundCallResponse:
        return OutboundCallResponse(
            call_id="tg-12345",
            status="active",
            detail="mocked outbound call",
            provider="telegram_mtproto",
            chat_id=12345,
        )

    monkeypatch.setattr(SecretaryService, "start_outbound_call", fake_start_outbound_call)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/calls/outbound",
            json={
                "target_user": "@alice",
                "purpose": "reminder",
                "metadata": {},
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "active"
    assert payload["provider"] == "telegram_mtproto"
    assert payload["chat_id"] == 12345


def test_transcript_route_persists_call_record() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        write = client.post(
            "/api/v1/calls/tg-555/transcript",
            json={"transcript": "Caller asked for a reminder tomorrow", "metadata": {}},
        )
        read = client.get("/api/v1/calls/tg-555")

    assert write.status_code == 200
    assert read.status_code == 200
    payload = read.json()
    transcripts = payload.get("transcripts") or []
    assert transcripts
    assert "reminder tomorrow" in transcripts[-1]["text"]


def test_agent_reply_route_works_with_mock(monkeypatch) -> None:
    async def fake_agent_reply(self, call_id: str, transcript: str, context: dict) -> AgentReplyResponse:
        return AgentReplyResponse(
            call_id=call_id,
            reply=f"handled:{transcript}",
            action_items=["update_calendar", "notify_customer"],
        )

    monkeypatch.setattr(SecretaryService, "generate_agent_reply", fake_agent_reply)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/agent/reply",
            json={
                "call_id": "tg-77",
                "transcript": "Please reschedule to Monday at 9",
                "context": {},
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"].startswith("handled:")
    assert payload["action_items"] == ["update_calendar", "notify_customer"]


def test_agent_analyze_route_works_with_mock(monkeypatch) -> None:
    async def fake_agent_analyze(self, call_id: str, transcript: str, context: dict) -> AgentAnalyzeResponse:
        return AgentAnalyzeResponse(
            call_id=call_id,
            intent="reschedule_event",
            confidence=0.92,
            reply="Sure, I can help reschedule that.",
            requires_human=False,
            transfer_reason=None,
            action_items=["Find available slots", "Confirm preferred time"],
            extracted_fields={"date": "Tuesday", "time": "15:00"},
            model="glm-5.1",
        )

    monkeypatch.setattr(SecretaryService, "analyze_agent_turn", fake_agent_analyze)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/agent/analyze",
            json={
                "call_id": "tg-88",
                "transcript": "Can you move my meeting to Tuesday at 3?",
                "context": {"customer_name": "Alex"},
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "reschedule_event"
    assert payload["confidence"] == 0.92
    assert payload["reply"].startswith("Sure")
    assert payload["action_items"] == ["Find available slots", "Confirm preferred time"]


def test_agent_live_respond_route_works_with_mock(monkeypatch) -> None:
    async def fake_live_respond(
        self,
        call_id: str,
        transcript: str,
        context: dict,
        speak_response: bool,
    ) -> AgentLiveRespondResponse:
        return AgentLiveRespondResponse(
            call_id=call_id,
            transcript=transcript,
            reply="Sure, I can move that.",
            intent="reschedule_event",
            confidence=0.9,
            requires_human=False,
            transfer_reason=None,
            action_items=["Find available times"],
            extracted_fields={"date": "Tuesday"},
            model="glm-5.1",
            tts_audio_path=".telegram/audio/generated/tg-77.mp3",
            tts_status="generated",
            call_audio_status="streaming_out",
        )

    monkeypatch.setattr(SecretaryService, "live_agent_respond", fake_live_respond)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/agent/live/respond",
            json={
                "call_id": "tg-77",
                "transcript": "Please reschedule this.",
                "context": {"source": "test"},
                "speak_response": True,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "reschedule_event"
    assert payload["reply"].startswith("Sure")
    assert payload["tts_status"] == "generated"
    assert payload["call_audio_status"] == "streaming_out"


def test_call_events_endpoint_returns_transcript_event() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        client.post(
            "/api/v1/calls/tg-321/transcript",
            json={"transcript": "test event", "metadata": {}},
        )
        response = client.get("/api/v1/calls/events?limit=10")

    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert any(event.get("type") == "transcript_received" for event in events)


def test_live_websocket_ping_roundtrip() -> None:
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        with client.websocket_connect("/api/v1/ws/live/tg-900") as ws:
            connected = ws.receive_json()
            assert connected["type"] == "connected"
            assert connected["call_id"] == "tg-900"

            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
            assert pong["call_id"] == "tg-900"


def test_live_websocket_transcript_triggers_agent_response(monkeypatch) -> None:
    async def fake_live_respond(
        self,
        call_id: str,
        transcript: str,
        context: dict,
        speak_response: bool,
    ) -> AgentLiveRespondResponse:
        return AgentLiveRespondResponse(
            call_id=call_id,
            transcript=transcript,
            reply="I can help with that now.",
            intent="general_query",
            confidence=0.75,
            requires_human=False,
            transfer_reason=None,
            action_items=["confirm_time"],
            extracted_fields={"topic": "reschedule"},
            model="glm-5.1",
            tts_audio_path=".telegram/audio/generated/tg-900.mp3",
            tts_status="generated",
            call_audio_status="streaming_out",
        )

    monkeypatch.setattr(SecretaryService, "live_agent_respond", fake_live_respond)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        with client.websocket_connect("/api/v1/ws/live/tg-900") as ws:
            ws.receive_json()  # connected event
            ws.send_json(
                {
                    "type": "transcript",
                    "transcript": "Can we move my meeting?",
                    "context": {"source": "test"},
                    "speak_response": True,
                }
            )
            event = ws.receive_json()

    assert event["type"] == "agent_response"
    payload = event["data"]
    assert payload["reply"] == "I can help with that now."
    assert payload["tts_status"] == "generated"


def test_start_telegram_live_loop_route_works_with_mock(monkeypatch) -> None:
    async def fake_start_live(self, call_id: str, payload) -> TelegramLiveAgentResponse:
        return TelegramLiveAgentResponse(
            call_id=call_id,
            status="running",
            detail="mock start",
            recording_path=".telegram/audio/recordings/tg-10.wav",
            stt_status="waiting_audio",
            speak_response=True,
        )

    monkeypatch.setattr(SecretaryService, "start_telegram_live_agent", fake_start_live)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/calls/tg-10/live/start",
            json={"context": {"source": "test"}, "speak_response": True},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["recording_path"].endswith("tg-10.wav")


def test_telegram_live_status_route_works_with_mock(monkeypatch) -> None:
    async def fake_status(self, call_id: str) -> TelegramLiveAgentStatusResponse:
        return TelegramLiveAgentStatusResponse(
            call_id=call_id,
            running=True,
            status="running",
            detail="mock status",
            recording_path=".telegram/audio/recordings/tg-11.wav",
            last_stt_status="ok",
            last_transcript="hello there",
        )

    monkeypatch.setattr(SecretaryService, "telegram_live_agent_status", fake_status)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/calls/tg-11/live/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["running"] is True
    assert payload["last_stt_status"] == "ok"


def test_stop_telegram_live_loop_route_works_with_mock(monkeypatch) -> None:
    async def fake_stop_live(self, call_id: str) -> TelegramLiveAgentResponse:
        return TelegramLiveAgentResponse(
            call_id=call_id,
            status="stopped",
            detail="mock stop",
            recording_path=".telegram/audio/recordings/tg-12.wav",
            stt_status="ok",
            speak_response=True,
        )

    monkeypatch.setattr(SecretaryService, "stop_telegram_live_agent", fake_stop_live)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/calls/tg-12/live/stop")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "stopped"
