from fastapi.testclient import TestClient

from secretary_ai.main import create_app


def test_health_reports_scaffold_mode() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "scaffold_only"


def test_architecture_endpoint_exists() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/architecture")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "scaffold_only"
    assert "API Layer (FastAPI routes)" in payload["components"]
