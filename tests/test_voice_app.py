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
        timezone="Europe/London",
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
    assert "ws://127.0.0.1:*" in response.headers["content-security-policy"]
    assert "wss://generativelanguage.googleapis.com" in response.headers["content-security-policy"]
    assert response.headers["permissions-policy"].startswith("microphone=(self)")
    assert {"transcript-dialog", "settings-dialog", "access-dialog"} <= parser.dialogs
    assert {"access-key", "language-select", "microphone-select"} <= parser.labels
    assert all(button.get("type") == "button" or button.get("type") == "submit" for button in parser.buttons)
    settings_button = next(button for button in parser.buttons if button.get("id") == "settings-button")
    assert settings_button["aria-haspopup"] == "dialog"
    assert settings_button["aria-controls"] == "settings-dialog"
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
    assert 'secretary-voice-v11' in worker.text
    assert 'fetch(event.request)' in worker.text
    assert 'new Response("Secretary is temporarily unavailable."' in worker.text


def test_voice_page_versions_connection_critical_assets() -> None:
    client, _ = _client()
    page = client.get("/voice/").text

    assert voice_app._VOICE_ASSET_VERSION == "11"
    assert '/voice/app.js?v=11' in page
    assert '/voice/app.css?v=11' in page
    assert '/voice/audio-worklet.js?v=11' in voice_app.VOICE_JS


def test_voice_settings_are_local_and_use_real_readiness_endpoints() -> None:
    assert 'localStorage.setItem("voiceLanguage"' in voice_app.VOICE_JS
    assert 'localStorage.setItem("voiceMicrophoneId"' in voice_app.VOICE_JS
    assert 'fetchJSON("/api/v1/health")' in voice_app.VOICE_JS
    assert 'fetchJSON("/api/v1/calendar/oauth/status")' in voice_app.VOICE_JS
    assert 'fetchJSON("/api/v1/telegram/auth/status")' in voice_app.VOICE_JS
    assert "getFloatTimeDomainData" in voice_app.VOICE_JS
    assert "Microphone input level" in voice_app.VOICE_HTML


def test_voice_setup_uses_raw_websocket_generation_config_schema() -> None:
    setup = voice_app.VOICE_JS.split("function setupMessage()", 1)[1].split(
        "function openSocket()", 1
    )[0]

    assert 'generationConfig: {' in setup
    assert 'generationConfig: {\n        responseModalities: ["AUDIO"],\n        speechConfig: {' in setup
    assert "silenceDurationMs: 500" in setup
    assert 'activityHandling: "START_OF_ACTIVITY_INTERRUPTS"' in setup
    assert 'turnCoverage: "TURN_INCLUDES_ONLY_ACTIVITY"' in setup
    assert '"manage_calendar"' in setup
    assert 'enum: ["read", "create", "cancel", "reminder"]' in setup
    assert '"plan_route"' in setup
    assert '"remember_fact"' in setup


def test_voice_client_handles_stream_end_and_local_barge_in() -> None:
    assert "audioStreamEnd: true" in voice_app.VOICE_JS
    assert "app.localSpeechFrames >= 2" in voice_app.VOICE_JS
    assert "app.localBargeIn = true" in voice_app.VOICE_JS
    assert "secretary-playback" in voice_app.AUDIO_WORKLET_JS
    assert "CAPTURE_SAMPLES = 320" in voice_app.AUDIO_WORKLET_JS
    assert "direct_websocket_url" in voice_app.VOICE_JS
    assert "prefetchToken()" in voice_app.VOICE_JS
    assert "prefetchAudioGraph()" in voice_app.VOICE_JS
    assert "latency: 0" in voice_app.VOICE_JS
    assert "flushPendingAudio()" in voice_app.VOICE_JS
    assert "openSocket();" in voice_app.VOICE_JS
    assert "await audioReady" in voice_app.VOICE_JS
    assert "handleToolCalls(message.toolCall.functionCalls).catch" in voice_app.VOICE_JS
    assert "droppedAudioChunks += 1" in voice_app.VOICE_JS
    assert "message.toolCallCancellation?.ids" in voice_app.VOICE_JS
    assert "app.toolResults.has(call.id)" in voice_app.VOICE_JS
    assert "The live connection timed out. Tap Retry." in voice_app.VOICE_JS
    assert "nvidia broadcast|virtual|screaming bee" in voice_app.VOICE_JS
    assert "is sending silence. Choose a working microphone" in voice_app.VOICE_JS
    assert "if (output) output.set(input);" in voice_app.AUDIO_WORKLET_JS


async def test_voice_relay_decodes_binary_json_for_browser() -> None:
    class _Browser:
        def __init__(self) -> None:
            self.messages: list[str] = []

        async def send_text(self, message: str) -> None:
            self.messages.append(message)

    class _Upstream:
        def __init__(self) -> None:
            self.sent = False

        def __aiter__(self):
            return self

        async def __anext__(self) -> bytes:
            if self.sent:
                raise StopAsyncIteration
            self.sent = True
            return b'{"setupComplete":{}}'

    browser = _Browser()
    stats = {
        "setup_complete": 0,
        "transcription_chars": 0,
        "output_chunks": 0,
        "output_audio_chars": 0,
        "completed_turns": 0,
    }
    await voice_app._relay_gemini_messages(browser, _Upstream(), stats, "voice-test")

    assert browser.messages == ['{"setupComplete":{}}']
    assert stats["setup_complete"] == 1


async def test_voice_relay_forwards_browser_audio_before_stats() -> None:
    order: list[str] = []

    class _Browser:
        def __init__(self) -> None:
            self._sent = False

        async def receive(self) -> dict[str, str]:
            if self._sent:
                return {"type": "websocket.disconnect"}
            self._sent = True
            return {
                "type": "websocket.receive",
                "text": '{"realtimeInput":{"audio":{"data":"AQA="}}}',
            }

    class _Upstream:
        async def send(self, text: str) -> None:
            order.append("forward")
            assert "realtimeInput" in text

    stats = {
        "input_chunks": 0,
        "input_bytes": 0,
        "input_peak": 0,
        "invalid_audio_chunks": 0,
    }
    original = voice_app._record_relay_input_stats

    def tracked(text, stats, call_id):
        order.append("stats")
        original(text, stats, call_id)

    voice_app._record_relay_input_stats = tracked
    try:
        await voice_app._relay_browser_messages(_Browser(), _Upstream(), stats, "voice-test")
    finally:
        voice_app._record_relay_input_stats = original

    assert order == ["forward", "stats"]
    assert stats["input_chunks"] == 1


def test_voice_token_requires_configured_access_key(monkeypatch) -> None:
    class _Tokens:
        @staticmethod
        def create(*, config):
            warnings.warn(
                "The SDK's token creation implementation is experimental, and may change",
                stacklevel=2,
            )
            assert config["uses"] == 1
            assert config["lock_additional_fields"] == []
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
    monkeypatch.setattr(voice_app.secrets, "token_urlsafe", lambda _: "relay-ticket")
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
    assert response.json()["token"] == "relay-ticket"
    assert response.json()["live_token"] == "auth_tokens/short-lived"
    assert response.json()["timezone"] == "Europe/London"
    assert response.json()["websocket_url"] == "ws://testserver/api/v1/voice/live"
    assert response.json()["direct_websocket_url"].startswith(
        "wss://generativelanguage.googleapis.com/ws/"
    )
    stored_token, _ = client.app.state.voice_relay_tickets["relay-ticket"]
    assert stored_token == "auth_tokens/short-lived"
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


def test_voice_route_tool_bypasses_general_reasoning_pipeline() -> None:
    client, secretary = _client("key")
    calls = []

    async def plan_route(origin: str, destination: str, mode: str):
        calls.append((origin, destination, mode))
        return {
            "status": "success",
            "details": "ETA 24 mins, distance 18 km (driving).",
            "eta_minutes": 24,
        }

    secretary.maps = SimpleNamespace(plan_route=plan_route)
    response = client.post(
        "/api/v1/voice/action",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "tool": "plan_route",
            "arguments": {
                "origin": "London",
                "destination": "Heathrow",
                "mode": "driving",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"].startswith("ETA 24")
    assert calls == [("London", "Heathrow", "driving")]


def test_voice_calendar_tool_processes_queued_action() -> None:
    client, secretary = _client("key")

    async def queue(**kwargs):
        assert kwargs["transcript"] == "Move lunch to 2 PM"
        assert kwargs["context"]["calendar_operation"] == "create"
        return {"status": "queued", "queued": True, "task_id": "cal-1"}

    async def process(call_id: str, task_id: str):
        assert (call_id, task_id) == ("voice-123", "cal-1")
        return {"status": "done", "reply": "Lunch moved to 2 PM."}

    secretary.calendar = SimpleNamespace(quick_reply_or_enqueue=queue)
    secretary._process_queued_calendar_task = process
    response = client.post(
        "/api/v1/voice/action",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "tool": "manage_calendar",
            "arguments": {"operation": "create", "request": "Move lunch to 2 PM"},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["reply"] == "Lunch moved to 2 PM."


def test_voice_memory_and_booking_tools_use_direct_services() -> None:
    client, secretary = _client("key")
    saved = []

    def remember(call_id: str, transcript: str):
        saved.append((call_id, transcript))
        return {"fact": transcript.removeprefix("remember that ")}

    def recall(query: str, limit: int):
        assert (query, limit) == ("dentist", 3)
        return [{"fact": "My dentist is Dr Khan."}]

    async def search_by_action(action: str, payload: str, extracted: dict):
        assert (action, payload, extracted["location"]) == (
            "find_restaurant",
            "quiet Italian",
            "Soho",
        )
        return {
            "category": "restaurants",
            "location": "Soho",
            "results": [{"title": "Example"}],
            "voice_summary": "I found one quiet Italian restaurant.",
        }

    secretary.memory = SimpleNamespace(
        add_user_fact_if_requested=remember,
        retrieve_user_fact=recall,
    )
    secretary.booking = SimpleNamespace(search_by_action=search_by_action)

    remembered = client.post(
        "/api/v1/voice/action",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "tool": "remember_fact",
            "arguments": {"fact": "My dentist is Dr Khan."},
        },
    )
    recalled = client.post(
        "/api/v1/voice/action",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "tool": "recall_memory",
            "arguments": {"query": "dentist"},
        },
    )
    booking = client.post(
        "/api/v1/voice/action",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "tool": "search_booking",
            "arguments": {
                "category": "restaurant",
                "location": "Soho",
                "details": "quiet Italian",
            },
        },
    )

    assert remembered.json()["status"] == "saved"
    assert recalled.json()["data"]["facts"] == ["My dentist is Dr Khan."]
    assert booking.json()["data"]["result_count"] == 1
    assert saved == [("voice-123", "remember that My dentist is Dr Khan.")]


def test_voice_booking_does_not_count_provider_errors_as_results() -> None:
    client, secretary = _client("key")

    async def search_by_action(action: str, payload: str, extracted: dict):
        return {
            "category": "restaurants",
            "location": "Soho",
            "results": [{"error": "Tavily API key is not configured."}],
            "voice_summary": "No results are available right now.",
        }

    secretary.booking = SimpleNamespace(search_by_action=search_by_action)
    response = client.post(
        "/api/v1/voice/action",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "tool": "search_booking",
            "arguments": {"category": "restaurant", "location": "Soho"},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    assert response.json()["data"]["result_count"] == 0


def test_voice_metrics_accepts_bounded_content_free_summary(caplog) -> None:
    client, _ = _client("key")
    caplog.set_level("INFO", logger=voice_app.__name__)
    response = client.post(
        "/api/v1/voice/metrics",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "session_ms": 5000,
            "response_count": 2,
            "response_latency_ms_total": 1200,
            "response_latency_ms_max": 700,
            "barge_in_attempt_count": 1,
            "interruption_count": 1,
            "interruption_latency_ms_total": 140,
            "tool_call_count": 1,
            "tool_latency_ms_total": 400,
            "tool_latency_ms_max": 400,
            "dropped_audio_chunks": 0,
            "reconnect_count": 0,
        },
    )

    assert response.status_code == 204
    assert "response_avg_ms=600" in caplog.text
    assert "transcript" not in caplog.text

    rejected = client.post(
        "/api/v1/voice/metrics",
        headers={"X-Voice-App-Key": "key"},
        json={
            "call_id": "voice-123",
            "session_ms": 1,
            "response_count": 0,
            "response_latency_ms_total": 0,
            "response_latency_ms_max": 0,
            "barge_in_attempt_count": 0,
            "interruption_count": 0,
            "interruption_latency_ms_total": 0,
            "tool_call_count": 0,
            "tool_latency_ms_total": 0,
            "tool_latency_ms_max": 0,
            "dropped_audio_chunks": 0,
            "reconnect_count": 0,
            "transcript": "must never be accepted",
        },
    )
    assert rejected.status_code == 422


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
