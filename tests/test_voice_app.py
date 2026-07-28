from html.parser import HTMLParser
from types import SimpleNamespace
import warnings

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secretary_ai.ui import voice_app


class _VoiceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str | None]] = []
        self.dialogs: set[str] = set()
        self.labels: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "button":
            self.buttons.append(values)
        elif tag == "dialog" and values.get("id"):
            self.dialogs.add(str(values["id"]))
        elif tag == "label" and values.get("for"):
            self.labels.add(str(values["for"]))


def _client(
    access_key: str | None = None,
    base_url: str = "http://testserver",
) -> tuple[TestClient, SimpleNamespace]:
    settings = SimpleNamespace(
        voice_app_access_key=access_key,
        gemini_live_enabled=True,
        gemini_api_key="server-secret",
        gemini_live_api_version="v1beta",
        gemini_live_model="gemini-3.1-flash-live-preview",
        gemini_live_voice="Zephyr",
        language="en",
    )
    secretary = SimpleNamespace(settings=settings)
    app = FastAPI()
    app.state.secretary = secretary
    app.include_router(voice_app.router)
    return TestClient(app, base_url=base_url), secretary


def test_voice_page_is_accessible_and_hardened() -> None:
    client, _ = _client()
    response = client.get("/voice/")
    parser = _VoiceParser()
    parser.feed(response.text)

    assert response.status_code == 200
    assert "wss://generativelanguage.googleapis.com" in response.headers["content-security-policy"]
    assert response.headers["permissions-policy"].startswith("microphone=(self)")
    assert {"transcript-dialog", "access-dialog"} <= parser.dialogs
    assert "access-key" in parser.labels
    assert all(button.get("type") == "button" or button.get("type") == "submit" for button in parser.buttons)
    assert "server-secret" not in response.text
    assert "GEMINI_API_KEY" not in voice_app.VOICE_JS


def test_voice_manifest_and_service_worker_scope() -> None:
    client, _ = _client()

    manifest = client.get("/voice/manifest.webmanifest")
    worker = client.get("/voice/sw.js")

    assert manifest.json()["start_url"] == "/voice/"
    assert manifest.json()["display"] == "standalone"
    assert worker.headers["service-worker-allowed"] == "/voice/"
    assert "/api/" in worker.text
    assert 'secretary-voice-v3' in worker.text
    assert 'fetch(event.request)' in worker.text


def test_voice_page_versions_connection_critical_assets() -> None:
    client, _ = _client()
    page = client.get("/voice/").text

    assert '/voice/app.js?v=3' in page
    assert '/voice/app.css?v=3' in page
    assert '/voice/audio-worklet.js?v=3' in voice_app.VOICE_JS


def test_voice_setup_uses_raw_websocket_generation_config_schema() -> None:
    setup = voice_app.VOICE_JS.split("function setupMessage()", 1)[1].split(
        "function openSocket()", 1
    )[0]

    assert 'generationConfig: {' in setup
    assert 'generationConfig: {\n        responseModalities: ["AUDIO"],\n        speechConfig: {' in setup


def test_voice_token_requires_configured_access_key(monkeypatch) -> None:
    class _Tokens:
        @staticmethod
        def create(*, config):
            warnings.warn(
                "The SDK's token creation implementation is experimental, and may change",
                stacklevel=2,
            )
            assert config["uses"] == 1
            assert config["live_connect_constraints"]["model"] == "gemini-3.1-flash-live-preview"
            assert config["live_connect_constraints"]["config"] == {
                "response_modalities": ["AUDIO"]
            }
            return SimpleNamespace(name="auth_tokens/short-lived")

    class _Client:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "server-secret"
            assert kwargs["http_options"]["api_version"] == "v1beta"
            self.auth_tokens = _Tokens()

        def close(self) -> None:
            pass

    monkeypatch.setattr(voice_app.genai, "Client", _Client)
    client, _ = _client("correct-horse")

    assert client.post("/api/v1/voice/session-token").status_code == 401
    assert (
        client.post(
            "/api/v1/voice/session-token",
            headers={"X-Voice-App-Key": "wrong"},
        ).status_code
        == 401
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = client.post(
            "/api/v1/voice/session-token",
            headers={"X-Voice-App-Key": "correct-horse"},
        )
    assert response.status_code == 200
    assert caught == []
    assert response.json()["token"] == "auth_tokens/short-lived"
    assert "BidiGenerateContentConstrained" in response.json()["websocket_url"]
    assert response.headers["cache-control"] == "no-store"


def test_remote_voice_token_fails_closed_without_access_key() -> None:
    client, _ = _client(base_url="https://secretary.example")

    response = client.post("/api/v1/voice/session-token")

    assert response.status_code == 503
    assert "VOICE_APP_ACCESS_KEY" in response.json()["detail"]


def test_voice_token_turns_provider_auth_failure_into_actionable_error(monkeypatch) -> None:
    class _Rejected(Exception):
        code = 403

    class _Tokens:
        @staticmethod
        def create(*, config):
            raise _Rejected("provider detail must stay private")

    class _Client:
        def __init__(self, **kwargs):
            self.auth_tokens = _Tokens()

        def close(self) -> None:
            pass

    monkeypatch.setattr(voice_app.genai, "Client", _Client)
    client, _ = _client("key")

    response = client.post(
        "/api/v1/voice/session-token",
        headers={"X-Voice-App-Key": "key"},
    )

    assert response.status_code == 502
    assert "Replace GEMINI_API_KEY" in response.json()["detail"]
    assert "provider detail" not in response.text


def test_voice_action_reuses_secretary_pipeline() -> None:
    client, secretary = _client("key")
    calls = []

    async def respond(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            reply="Moved it to 3 PM.",
            intent=SimpleNamespace(value="calendar_update"),
            action_items=["calendar_processed:done"],
            requires_human=False,
        )

    secretary.live_agent_respond = respond
    response = client.post(
        "/api/v1/voice/action",
        headers={"X-Voice-App-Key": "key"},
        json={"call_id": "voice-123", "request": "Move the meeting to 3 PM"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Moved it to 3 PM."
    assert calls == [
        {
            "call_id": "voice-123",
            "transcript": "Move the meeting to 3 PM",
            "context": {"source": "voice_app"},
            "speak_response": False,
        }
    ]


def test_approved_palette_meets_contrast_targets() -> None:
    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(foreground: str, background: str) -> float:
        light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    assert contrast("#f0fdf4", "#09090b") >= 4.5
    assert contrast("#b4b4bd", "#09090b") >= 4.5
    assert contrast("#b4b4bd", "#18181b") >= 4.5
    assert contrast("#04130e", "#10b981") >= 4.5
    assert contrast("#ffffff", "#ef4444") >= 3
