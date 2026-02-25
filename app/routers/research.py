import json
import re
from typing import Annotated
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import SessionUser, require_role
from app.models.research import (
    ConversationCreate,
    ConversationMetaUpdate,
    ResearchFollowUpRequest,
    ResearchQueryRequest,
)
from app.prompts.research import (
    build_system_prompt,
    build_title_prompt,
    build_user_message,
)
from app.repositories import research as research_repo
from app.repositories import activity as activity_repo
from app.services.anthropic_client import get_client

router = APIRouter(prefix="/research", tags=["research"])


# --------------- Conversation CRUD ---------------


@router.get("/conversations")
async def list_conversations(
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
    search: str | None = Query(None),
    limit: int = Query(default=50, le=200),
):
    return await research_repo.list_conversations(user.id, search, limit)


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreate,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    conv_id = await research_repo.create_conversation(user.id, body.title, body.case_id, body.mode)
    await activity_repo.log_activity(user.id, "created", "research", conv_id, body.title)
    return {"id": conv_id}


@router.get("/conversations/{conv_id}")
async def get_conversation(
    conv_id: str,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    conv = await research_repo.get_conversation(conv_id, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: str,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    await research_repo.delete_conversation(conv_id, user.id)
    await activity_repo.log_activity(user.id, "deleted", "research", conv_id)
    return {"success": True}


@router.post("/conversations/{conv_id}/pin")
async def toggle_pin(
    conv_id: str,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    pinned = await research_repo.toggle_pin(conv_id, user.id)
    return {"pinned": pinned}


@router.patch("/conversations/{conv_id}/meta")
async def update_meta(
    conv_id: str,
    body: ConversationMetaUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    await research_repo.update_meta(conv_id, user.id, body.legal_areas, body.case_id)
    return {"success": True}


@router.get("/conversations/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    return await research_repo.get_messages(conv_id, user.id)


# --------------- Streaming / AI endpoints ---------------


@router.post("/query")
async def research_query(
    body: ResearchQueryRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    """Handle initial research query: create conversation, RAG search, stream AI response, save."""
    from app.rag.service import search as rag_search

    # 1. Create conversation if needed
    conv_id = body.conversation_id
    is_new = not conv_id
    if not conv_id:
        conv_id = await research_repo.create_conversation(
            user.id, "New Research", body.case_id, "case_linked" if body.case_id else "general"
        )

    # 2. Save user message
    await research_repo.save_message(conv_id, "user", body.question)

    # 3. RAG search
    rag_results: list[dict] = []
    try:
        rag_results = await rag_search({
            "query": body.question,
            "limit": 8,
        })
    except Exception:
        pass

    # 4. Build prompts
    system_prompt = build_system_prompt(body.case_context)
    messages = build_user_message(body.question, rag_results)

    # 5. SSE stream
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send meta event
            yield f"data: {json.dumps({'meta': {'conversationId': conv_id, 'ragResults': _format_rag_for_meta(rag_results)}})}\n\n"

            client = get_client()
            model = settings.ai_models.get("research", "claude-sonnet-4-20250514")
            full_text = ""

            with client.messages.stream(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    yield f"data: {json.dumps({'text': text})}\n\n"

            # Parse structured response and extract citations
            structured = _parse_structured_xml(full_text)
            citations = _extract_citations(full_text)

            # Save assistant message
            msg_id = await research_repo.save_message(
                conv_id, "assistant", full_text, structured, citations, rag_results
            )

            # Generate title for new conversations
            title = None
            if is_new:
                try:
                    title_model = settings.ai_models.get("title_generation", "claude-sonnet-4-20250514")
                    title_msg = client.messages.create(
                        model=title_model,
                        max_tokens=50,
                        messages=[{"role": "user", "content": build_title_prompt(body.question)}],
                    )
                    tb = next((b for b in title_msg.content if b.type == "text"), None)
                    if tb:
                        title = tb.text.strip()
                        await research_repo.update_title(conv_id, title)
                except Exception:
                    pass

            yield f"data: {json.dumps({'complete': {'messageId': msg_id, 'title': title}})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/follow-up")
async def research_follow_up(
    body: ResearchFollowUpRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    """Handle follow-up research query within an existing conversation."""
    from app.rag.service import search as rag_search

    # 1. Verify conversation exists
    conv = await research_repo.get_conversation(body.conversation_id, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    existing_messages = await research_repo.get_messages(body.conversation_id, user.id)

    # 2. Save user message
    await research_repo.save_message(body.conversation_id, "user", body.question)

    # 3. RAG search
    rag_results: list[dict] = []
    try:
        rag_results = await rag_search({
            "query": body.question,
            "limit": 8,
        })
    except Exception:
        pass

    # 4. Build prompts with history
    system_prompt = build_system_prompt(body.case_context)
    history = [{"role": m.get("role", ""), "content": m.get("content", "")} for m in existing_messages]
    messages = build_user_message(body.question, rag_results, history)

    # 5. SSE stream
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {json.dumps({'meta': {'conversationId': body.conversation_id, 'ragResults': _format_rag_for_meta(rag_results)}})}\n\n"

            client = get_client()
            model = settings.ai_models.get("research", "claude-sonnet-4-20250514")
            full_text = ""

            with client.messages.stream(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    yield f"data: {json.dumps({'text': text})}\n\n"

            structured = _parse_structured_xml(full_text)
            citations = _extract_citations(full_text)

            msg_id = await research_repo.save_message(
                body.conversation_id, "assistant", full_text, structured, citations, rag_results
            )

            yield f"data: {json.dumps({'complete': {'messageId': msg_id}})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# --------------- Helpers ---------------


def _format_rag_for_meta(rag_results: list[dict]) -> list[dict]:
    """Format RAG results for the meta SSE event."""
    return [
        {
            "precedent": r.get("judgment", r),
            "relevanceScore": r.get("relevanceScore", r.get("score", 0)),
            "matchedKeywords": r.get("matchedKeywords", []),
            "matchedAreas": r.get("matchedAreas", []),
        }
        for r in rag_results
    ]


def _parse_structured_xml(text: str) -> dict | None:
    """Parse structured XML tags from research response."""
    sections = ["summary", "applicable_law", "precedents", "analysis", "contrary_views"]
    result: dict[str, str] = {}

    for section in sections:
        match = re.search(rf"<{section}>([\s\S]*?)</{section}>", text, re.IGNORECASE)
        if match:
            result[section] = match.group(1).strip()

    return result if result else None


def _extract_citations(text: str) -> list[dict]:
    """Extract Pakistani legal citations from text."""
    citation_regex = re.compile(
        r"([A-Z][a-zA-Z\s.]+(?:v\.?\s+[A-Z][a-zA-Z\s.]+)?)\s*\((\d{4}\s+(?:PLD|SCMR|CLC|PCrLJ|YLR|MLD|PLJ|NLR|ALD)\s+\w+\s+\d+)\)"
    )
    citations: list[dict] = []
    seen: set[str] = set()

    for match in citation_regex.finditer(text):
        citation = match.group(2).strip()
        if citation in seen:
            continue
        seen.add(citation)

        year_match = re.search(r"\d{4}", citation)
        citations.append({
            "id": f"cit-{len(citations) + 1}",
            "caseName": match.group(1).strip(),
            "citation": citation,
            "court": "Supreme Court of Pakistan" if "SC" in citation else "High Court",
            "year": year_match.group(0) if year_match else "",
            "relevance": "",
            "snippet": "",
        })

    return citations
