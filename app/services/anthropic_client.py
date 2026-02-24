"""Lazy singleton Anthropic client."""

import anthropic

from app.config import settings

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=4,
            timeout=120.0,
        )
    return _client
