from fastapi.testclient import TestClient

from secretary_ai.core.config import get_settings
from secretary_ai.domain.models import (
    AgentReplyResponse,
    ModelCheckResponse,
    OutboundCallResponse,
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
    assert "Secretary AI Telegram Lab" in response.text


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
