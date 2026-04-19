import httpx
from secretary_ai.core.config import Settings

TAVILY_URL = "https://api.tavily.com/search"

async def tavily_search(
    settings: Settings,
    query: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    search_depth: str = "basic",
) -> list[dict]:
    """
    Search the web via Tavily. Returns a list of {title, url, content, score} dicts.
    On error, returns a single-item list with an 'error' key.
    """
    if not settings.tavily_api_key:
        return [{"error": "Tavily API key is not configured."}]

    body = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    if include_domains:
        body["include_domains"] = include_domains

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TAVILY_URL, json=body)
        if resp.status_code != 200:
            return [{"error": f"Tavily {resp.status_code}: {resp.text[:200]}"}]
        data = resp.json()
        results = data.get("results", []) or []
        return [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content"),
                "score": r.get("score"),
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}"}]
