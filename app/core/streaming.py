"""Shared SSE streaming helpers for AI endpoints."""

import json
from collections.abc import AsyncGenerator

import sentry_sdk
from fastapi.responses import StreamingResponse

from app.services.anthropic_client import get_client
from app.config import settings


async def stream_anthropic(
    model_key: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 8192,
    on_text: callable = None,
    pre_events: list[dict] | None = None,
    post_callback: callable = None,
) -> StreamingResponse:
    """
    Create an SSE StreamingResponse that streams Anthropic messages.

    Args:
        model_key: Key into settings.ai_models (e.g., "generate", "research")
        messages: Chat messages
        system: Optional system prompt
        max_tokens: Max tokens to generate
        on_text: Optional callback(text_chunk) called for each text chunk
        pre_events: Optional events to send before streaming starts
        post_callback: Optional async callback(full_text) called after streaming completes
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send pre-events (e.g., meta with RAG results)
            if pre_events:
                for event in pre_events:
                    yield f"data: {json.dumps(event)}\n\n"

            client = get_client()
            model = settings.ai_models.get(model_key, "claude-sonnet-4-20250514")

            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if system:
                kwargs["system"] = system

            full_text = ""

            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    full_text += text
                    if on_text:
                        on_text(text)
                    yield f"data: {json.dumps({'text': text})}\n\n"

            # Post-streaming callback (e.g., save to DB)
            if post_callback:
                result = await post_callback(full_text)
                if result:
                    yield f"data: {json.dumps(result)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            sentry_sdk.capture_exception(e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
