"""Shared OpenAI-compatible HTTP client used by both the agent and the secretary."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from secretary_ai.core.config import Settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return a persistent httpx client, creating one if needed."""
    global _client  # noqa: PLW0603
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


async def close_client() -> None:
    """Close the shared httpx client gracefully."""
    global _client  # noqa: PLW0603
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def openai_chat_completion(
    settings: Settings, payload: dict[str, Any]
) -> dict[str, Any]:
    """Send a chat-completion request to the OpenAI-compatible endpoint."""
    if not settings.openai_api_key:
        return {"error": "Missing OPENAI_API_KEY in environment."}

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        client = _get_client()
        response = await client.post(
            url, headers=headers, json=payload,
            timeout=settings.openai_timeout_seconds,
        )
        if response.status_code >= 300:
            logger.warning(
                "OpenAI API error %d: %s", response.status_code, response.text[:200],
            )
            return {
                "error": f"Chat request failed ({response.status_code}).",
                "raw": response.text[:240],
            }
        return {"data": response.json()}
    except httpx.TimeoutException:
        logger.warning("OpenAI request timed out after %ss", settings.openai_timeout_seconds)
        return {"error": "Request timed out."}
    except Exception as exc:
        logger.warning("OpenAI connection error: %s", exc)
        return {"error": f"Connection error: {exc.__class__.__name__}"}


def extract_message(data: dict[str, Any]) -> dict[str, Any]:
    """Extract the assistant message from a chat-completion response."""
    choices = data.get("choices") or []
    if not choices:
        return {}
    msg = choices[0].get("message") or {}
    return msg if isinstance(msg, dict) else {}
