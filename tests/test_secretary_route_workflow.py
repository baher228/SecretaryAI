import asyncio

from secretary_ai.core.config import Settings
from secretary_ai.domain.models import IntentType
from secretary_ai.services.secretary import SecretaryService


def test_live_route_workflow_returns_eta_reply() -> None:
    secretary = SecretaryService(Settings(zai_api_key=None, google_maps_api_key="test-key"))

    async def fake_plan_route(origin: str, destination: str, mode: str = "driving") -> dict:
        return {
            "status": "success",
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "eta_text": "28 mins",
            "eta_minutes": 28,
            "distance_text": "19 km",
            "details": "ETA 28 mins, distance 19 km (driving).",
            "map_url": "https://www.google.com/maps/dir/?api=1",
        }

    secretary.maps.plan_route = fake_plan_route  # type: ignore[method-assign]

    response = asyncio.run(
        secretary.live_agent_respond(
            call_id="route-1",
            transcript="How long is the route from London to Heathrow Airport?",
            context={},
            speak_response=False,
        )
    )

    assert response.intent == IntentType.PLAN_ROUTE
    assert "Calculating route now." in response.reply
    assert "ETA is 28 mins" in response.reply
    assert any("route_lookup_started" == item for item in response.action_items)
    assert any("route_lookup_success" == item for item in response.action_items)
    assert response.extracted_fields.get("origin") == "London"
    assert response.extracted_fields.get("destination") == "Heathrow Airport"
    assert response.extracted_fields.get("eta_text") == "28 mins"
