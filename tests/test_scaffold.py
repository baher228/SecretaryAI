from fastapi.testclient import TestClient

from secretary_ai.core.config import get_settings
from secretary_ai.domain.models import ModelCheckResponse
from secretary_ai.main import create_app
from secretary_ai.services.secretary import SecretaryService


def test_health_reports_scaffold_mode() -> None:
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "scaffold_only"


def test_architecture_endpoint_exists() -> None:
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/api/v1/architecture")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "scaffold_only"
    assert "API Layer (FastAPI routes)" in payload["components"]


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
    client = TestClient(create_app())
    response = client.post("/api/v1/model/check", json={"prompt": "Say hello"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "z.ai"
    assert payload["connected"] is True
    assert payload["output"] == "echo:Say hello"
