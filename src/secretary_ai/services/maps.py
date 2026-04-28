from urllib.parse import quote_plus

import httpx

from secretary_ai.core.config import Settings


class MapService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def plan_route(self, origin: str, destination: str, mode: str = "driving") -> dict:
        origin_clean = str(origin or "").strip()
        destination_clean = str(destination or "").strip()
        mode_clean = self._normalize_mode(mode)

        if not origin_clean or not destination_clean:
            return {
                "status": "error",
                "detail": "Both origin and destination are required.",
                "origin": origin_clean,
                "destination": destination_clean,
                "mode": mode_clean,
            }

        api_key = str(self.settings.google_maps_api_key or "").strip()
        if not api_key:
            return {
                "status": "error",
                "detail": "Missing GOOGLE_MAPS_API_KEY in environment.",
                "origin": origin_clean,
                "destination": destination_clean,
                "mode": mode_clean,
                "map_url": self._build_maps_url(origin_clean, destination_clean, mode_clean),
            }

        try:
            payload = await self._fetch_distance_matrix(
                origin=origin_clean,
                destination=destination_clean,
                mode=mode_clean,
                api_key=api_key,
            )
        except Exception as exc:
            return {
                "status": "error",
                "detail": f"Google Maps request failed: {exc.__class__.__name__}",
                "origin": origin_clean,
                "destination": destination_clean,
                "mode": mode_clean,
                "map_url": self._build_maps_url(origin_clean, destination_clean, mode_clean),
            }

        top_status = str(payload.get("status") or "").upper()
        if top_status != "OK":
            return {
                "status": "error",
                "detail": f"Google Maps status: {top_status or 'UNKNOWN'}",
                "origin": origin_clean,
                "destination": destination_clean,
                "mode": mode_clean,
                "map_url": self._build_maps_url(origin_clean, destination_clean, mode_clean),
            }

        rows = payload.get("rows") or []
        elements = (rows[0].get("elements") if rows and isinstance(rows[0], dict) else []) or []
        element = elements[0] if elements and isinstance(elements[0], dict) else {}
        element_status = str(element.get("status") or "").upper()
        if element_status != "OK":
            return {
                "status": "error",
                "detail": f"No route found: {element_status or 'UNKNOWN'}",
                "origin": origin_clean,
                "destination": destination_clean,
                "mode": mode_clean,
                "map_url": self._build_maps_url(origin_clean, destination_clean, mode_clean),
            }

        duration_obj = element.get("duration_in_traffic") or element.get("duration") or {}
        duration_text = str(duration_obj.get("text") or "").strip()
        duration_seconds = int(duration_obj.get("value") or 0)
        distance_obj = element.get("distance") or {}
        distance_text = str(distance_obj.get("text") or "").strip()

        if not duration_text and duration_seconds > 0:
            duration_text = f"{max(1, round(duration_seconds / 60))} mins"
        eta_minutes = max(0, round(duration_seconds / 60)) if duration_seconds > 0 else None

        details = f"ETA {duration_text}" if duration_text else "ETA unavailable"
        if distance_text:
            details += f", distance {distance_text}"
        details += f" ({mode_clean})."

        return {
            "status": "success",
            "origin": origin_clean,
            "destination": destination_clean,
            "mode": mode_clean,
            "eta_text": duration_text or None,
            "eta_minutes": eta_minutes,
            "distance_text": distance_text or None,
            "details": details,
            "map_url": self._build_maps_url(origin_clean, destination_clean, mode_clean),
        }

    async def _fetch_distance_matrix(
        self,
        origin: str,
        destination: str,
        mode: str,
        api_key: str,
    ) -> dict:
        params = {
            "origins": origin,
            "destinations": destination,
            "mode": mode,
            "departure_time": "now",
            "units": "metric",
            "key": api_key,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params=params,
            )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        candidate = str(mode or "driving").strip().lower()
        if candidate in {"driving", "walking", "bicycling", "transit"}:
            return candidate
        return "driving"

    @staticmethod
    def _build_maps_url(origin: str, destination: str, mode: str) -> str:
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={quote_plus(origin)}"
            f"&destination={quote_plus(destination)}"
            f"&travelmode={quote_plus(mode)}"
        )
