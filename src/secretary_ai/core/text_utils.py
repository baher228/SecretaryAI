"""Shared text-processing utilities used across services."""

from __future__ import annotations


def normalize_text(s: str | None, *, lowercase: bool = False) -> str:
    """Collapse whitespace, strip, and optionally lowercase."""
    text = " ".join((s or "").split()).strip()
    return text.lower() if lowercase else text
