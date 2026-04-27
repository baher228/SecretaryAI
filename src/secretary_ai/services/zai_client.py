"""Shared Z.AI GLM HTTP client used by both the agent and the secretary."""

from typing import Any

import httpx

from secretary_ai.core.config import Settings


async def zai_chat_completion(settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
    """Send a chat-completion request to the Z.AI GLM endpoint."""
    if not settings.zai_api_key:
        return {"error": "Missing ZAI_API_KEY in environment."}

    url = f"{settings.zai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.zai_api_key}",
        "Content-Type": "application/json",
        "Accept-Language": "en-US,en",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.zai_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 300:
            return {
                "error": f"GLM request failed ({response.status_code}).",
                "raw": response.text[:240],
            }
        return {"data": response.json()}
    except Exception as exc:
        return {"error": f"Connection error: {exc.__class__.__name__}"}


def extract_message(data: dict[str, Any]) -> dict[str, Any]:
    """Extract the assistant message from a Z.AI chat-completion response."""
    choices = data.get("choices") or []
    if not choices:
        return {}
    msg = choices[0].get("message") or {}
    return msg if isinstance(msg, dict) else {}
