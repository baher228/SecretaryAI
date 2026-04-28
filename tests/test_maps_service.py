import asyncio

from secretary_ai.core.config import Settings
from secretary_ai.services.maps import MapService


def test_plan_route_returns_eta_from_google_payload() -> None:
    service = MapService(Settings(google_maps_api_key="test-key"))

    async def fake_fetch_distance_matrix(origin: str, destination: str, mode: str, api_key: str) -> dict:
        assert origin == "London"
        assert destination == "Heathrow Airport"
        assert mode == "driving"
        assert api_key == "test-key"
        return {
            "status": "OK",
            "rows": [
                {
                    "elements": [
                        {
                            "status": "OK",
                            "distance": {"text": "27.8 km", "value": 27800},
                            "duration": {"text": "35 mins", "value": 2100},
                            "duration_in_traffic": {"text": "42 mins", "value": 2520},
                        }
                    ]
                }
            ],
        }

    service._fetch_distance_matrix = fake_fetch_distance_matrix  # type: ignore[method-assign]

    result = asyncio.run(service.plan_route("London", "Heathrow Airport"))

    assert result["status"] == "success"
    assert result["eta_text"] == "42 mins"
    assert result["distance_text"] == "27.8 km"
    assert result["eta_minutes"] == 42
    assert "google.com/maps/dir" in str(result["map_url"])


def test_plan_route_requires_api_key() -> None:
    service = MapService(Settings(google_maps_api_key=None))

    result = asyncio.run(service.plan_route("London", "Manchester"))

    assert result["status"] == "error"
    assert "GOOGLE_MAPS_API_KEY" in str(result["detail"])
