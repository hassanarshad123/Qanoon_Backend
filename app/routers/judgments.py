import json
import re
from typing import Annotated
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import SessionUser, require_role
from app.core.streaming import stream_anthropic
from app.models.judgment import (
    JudgmentChatMessage,
    JudgmentChatStreamRequest,
    JudgmentCreate,
    JudgmentGenerateRequest,
    JudgmentRegenerateRequest,
    JudgmentSectionContentUpdate,
    JudgmentSectionReviewUpdate,
    JudgmentStatusUpdate,
)
from app.prompts.judgment import (
    build_chat_prompt,
    build_generation_prompt,
    build_regeneration_prompt,
)
from app.repositories import judgments as judgments_repo
from app.repositories import briefs as briefs_repo
from app.repositories import profiles as profiles_repo
from app.repositories import activity as activity_repo
from app.services.anthropic_client import get_client

router = APIRouter(prefix="/judgments", tags=["judgments"])


# --------------- CRUD endpoints ---------------


@router.post("")
async def create_judgment(
    body: JudgmentCreate,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    jid = await judgments_repo.create_judgment(user.id, body.model_dump())
    await activity_repo.log_activity(user.id, "created", "judgment", jid, body.case_title)
    return {"id": jid}


@router.get("")
async def list_judgments(user: Annotated[SessionUser, Depends(require_role("judge", "admin"))]):
    return await judgments_repo.list_judgments(user.id)


@router.get("/{judgment_id}")
async def get_judgment(judgment_id: str, user: Annotated[SessionUser, Depends(require_role("judge", "admin"))]):
    j = await judgments_repo.get_judgment(judgment_id, user.id)
    if not j:
        raise HTTPException(status_code=404, detail="Judgment not found")
    return j


@router.patch("/{judgment_id}/status")
async def update_status(
    judgment_id: str,
    body: JudgmentStatusUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    await judgments_repo.update_status(judgment_id, user.id, body.status)
    if body.status == "finalized":
        await activity_repo.log_activity(user.id, "finalized", "judgment", judgment_id)
    return {"success": True}


@router.delete("/{judgment_id}")
async def delete_judgment(judgment_id: str, user: Annotated[SessionUser, Depends(require_role("judge", "admin"))]):
    await judgments_repo.delete_judgment(judgment_id, user.id)
    await activity_repo.log_activity(user.id, "deleted", "judgment", judgment_id)
    return {"success": True}


@router.patch("/sections/{section_id}/content")
async def update_section_content(
    section_id: str,
    body: JudgmentSectionContentUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    await judgments_repo.update_section_content(section_id, user.id, body.content, body.increment_regeneration)
    return {"success": True}


@router.patch("/sections/{section_id}/review")
async def update_section_review(
    section_id: str,
    body: JudgmentSectionReviewUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    await judgments_repo.update_section_review(section_id, user.id, body.status, body.flag_note)
    return {"success": True}


@router.post("/{judgment_id}/chat")
async def save_chat(
    judgment_id: str,
    body: JudgmentChatMessage,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    msg_id = await judgments_repo.save_chat(judgment_id, user.id, body.role, body.content, body.citations)
    return {"id": msg_id}


# --------------- Streaming / AI endpoints ---------------


@router.post("/generate")
async def generate_judgment(
    body: JudgmentGenerateRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    """Generate a judgment with RAG search, streaming, section parsing, and DB save."""
    from app.rag.service import search as rag_search

    # Get brief content if starting from a brief
    brief_content: str | None = None
    extracted_data = body.case_data or {}

    if body.brief_id:
        brief = await briefs_repo.get_brief(body.brief_id, user.id)
        if brief:
            sections = brief.get("sections", [])
            brief_content = "\n\n".join(
                f"## {s.get('title', '')}\n{s.get('content', '')}" for s in sections
            )
            if brief.get("extractedData") or brief.get("extracted_data"):
                extracted_data = brief.get("extractedData") or brief.get("extracted_data")

    # RAG search for precedents
    search_query = " ".join(
        filter(None, [body.case_title, body.case_number, (extracted_data or {}).get("courtInfo", {}).get("caseType", "")])
    )
    rag_results: list[dict] = []
    try:
        results = await rag_search({"query": search_query, "limit": 8})
        rag_results = results
    except Exception:
        pass

    # Get judge profile
    judge_profile: dict | None = None
    try:
        judge_profile = await profiles_repo.get_judge_profile(user.id)
    except Exception:
        pass

    # Build prompt
    prompt = build_generation_prompt(extracted_data, brief_content, rag_results, judge_profile)

    # Build pre-events with RAG results
    pre_events = [
        {
            "meta": {
                "ragResults": [
                    {
                        "precedent": r.get("judgment", r),
                        "relevanceScore": r.get("relevanceScore", r.get("score", 0)),
                        "matchedKeywords": r.get("matchedKeywords", []),
                        "matchedAreas": r.get("matchedAreas", []),
                    }
                    for r in rag_results
                ],
            }
        }
    ]

    async def on_complete(full_text: str) -> dict | None:
        """Parse sections from XML and save judgment to DB."""
        sections = _parse_judgment_sections(full_text)
        judgment_id = await judgments_repo.create_judgment(user.id, {
            "case_title": body.case_title,
            "case_number": body.case_number,
            "court": body.court,
            "brief_id": body.brief_id,
            "case_data": extracted_data,
            "rag_results": rag_results,
            "sections": sections,
        })
        await activity_repo.log_activity(user.id, "created", "judgment", judgment_id, body.case_title)
        return {"complete": {"judgmentId": judgment_id}}

    return await stream_anthropic(
        model_key="generate",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16384,
        pre_events=pre_events,
        post_callback=on_complete,
    )


@router.post("/chat-stream")
async def chat_stream(
    body: JudgmentChatStreamRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    system, messages = build_chat_prompt(
        body.judgment_context,
        body.messages,
        body.user_message,
    )
    return await stream_anthropic(
        model_key="chat",
        messages=messages,
        system=system,
        max_tokens=4096,
    )


@router.post("/regenerate")
async def regenerate_section(
    body: JudgmentRegenerateRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "admin"))],
):
    prompt = build_regeneration_prompt(
        body.section_title,
        body.current_content,
        body.judge_note,
        body.judgment_context,
    )
    return await stream_anthropic(
        model_key="regenerate",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )


# --------------- Helpers ---------------


def _parse_judgment_sections(text: str) -> list[dict]:
    """Parse XML-delimited sections from generated judgment text."""
    section_regex = re.compile(
        r'<section\s+id="([^"]+)"\s+title="([^"]+)">([\s\S]*?)</section>'
    )
    sections = []
    for match in section_regex.finditer(text):
        sections.append({
            "sectionKey": match.group(1),
            "title": match.group(2),
            "content": match.group(3).strip(),
        })

    # Fallback: if no sections parsed, create a single section
    if not sections:
        sections.append({
            "sectionKey": "full_judgment",
            "title": "Judgment",
            "content": text.strip(),
        })

    return sections
