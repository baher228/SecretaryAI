import httpx
from bot.config import TAVILY_API_KEY

TAVILY_URL = "https://api.tavily.com/search"
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def tavily_search(
    query: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    search_depth: str = "basic",
) -> list[dict]:
    """
    Search the web via Tavily. Returns a list of {title, url, content, score} dicts.
    On error, returns a single-item list with an 'error' key.
    """
    body = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    if include_domains:
        body["include_domains"] = include_domains

    try:
        resp = await _get_client().post(TAVILY_URL, json=body)
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
