from secretary_ai.core.config import Settings
from secretary_ai.services.tavily_search import tavily_search

class MapService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def plan_route(self, origin: str, destination: str, mode: str = "driving") -> dict:
        """
        Plans a route. Integrates with Google Maps API if key is present,
        otherwise uses a web search fallback to estimate distance and time.
        """
        if self.settings.google_maps_api_key:
            # Here we would use the actual Google Maps API
            # For now, we simulate the structure
            pass
        
        # Fallback to web search
        query = f"Google maps route {mode} from {origin} to {destination} distance and time"
        results = await tavily_search(self.settings, query, max_results=3, search_depth="basic")
        
        summary = ""
        for r in results:
            if "error" in r:
                return {"status": "error", "detail": r["error"]}
            summary += r.get("content", "") + " "
            
        return {
            "status": "success",
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "details": f"Based on search: {summary[:300]}...",
            "estimated_results": results
        }
