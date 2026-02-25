import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.core.auth import SessionUser, require_role
from app.core.streaming import stream_anthropic
from app.models.brief import (
    BriefAnalyzeChunkRequest,
    BriefAnalyzeRequest,
    BriefChatStreamRequest,
    BriefCreate,
    BriefGenerateRequest,
    BriefPrecedentsRequest,
    BriefRegenerateRequest,
    BriefStatusUpdate,
    ChatMessage,
    SectionContentUpdate,
    SectionReviewUpdate,
)
from app.prompts.brief import (
    build_analysis_prompt,
    build_chat_prompt,
    build_generation_prompt,
    build_regeneration_prompt,
)
from app.prompts.precedent_ranking import build_ranking_prompt
from app.repositories import briefs as briefs_repo
from app.repositories import activity as activity_repo
from app.services.anthropic_client import get_client

router = APIRouter(prefix="/briefs", tags=["briefs"])


# --------------- CRUD endpoints ---------------


@router.post("")
async def create_brief(
    body: BriefCreate,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    brief_id = await briefs_repo.save_brief(user.id, body.model_dump())
    await activity_repo.log_activity(user.id, "created", "brief", brief_id, body.case_title)
    return {"id": brief_id}


@router.get("")
async def list_briefs(user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))]):
    return await briefs_repo.list_briefs(user.id)


@router.get("/{brief_id}")
async def get_brief(brief_id: str, user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))]):
    brief = await briefs_repo.get_brief(brief_id, user.id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return brief


@router.patch("/{brief_id}/status")
async def update_brief_status(
    brief_id: str,
    body: BriefStatusUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    await briefs_repo.update_brief_status(brief_id, user.id, body.status)
    if body.status == "finalized":
        await activity_repo.log_activity(user.id, "finalized", "brief", brief_id)
    return {"success": True}


@router.delete("/{brief_id}")
async def delete_brief(brief_id: str, user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))]):
    await briefs_repo.delete_brief(brief_id, user.id)
    await activity_repo.log_activity(user.id, "deleted", "brief", brief_id)
    return {"success": True}


@router.patch("/sections/{section_id}/review")
async def update_section_review(
    section_id: str,
    body: SectionReviewUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    await briefs_repo.update_section_review(section_id, user.id, body.status, body.flag_note)
    return {"success": True}


@router.patch("/sections/{section_id}/content")
async def update_section_content(
    section_id: str,
    body: SectionContentUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    await briefs_repo.update_section_content(section_id, user.id, body.content, body.increment_regeneration)
    return {"success": True}


@router.post("/{brief_id}/chat")
async def save_chat_message(
    brief_id: str,
    body: ChatMessage,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    msg_id = await briefs_repo.save_chat_message(brief_id, user.id, body.role, body.content, body.citations)
    return {"id": msg_id}


# --------------- Streaming / AI endpoints ---------------


@router.post("/generate")
async def generate_brief(
    body: BriefGenerateRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    prompt = build_generation_prompt(body.extracted_data, body.rag_results)
    return await stream_anthropic(
        model_key="generate",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16384,
    )


@router.post("/chat-stream")
async def chat_stream(
    body: BriefChatStreamRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    system, messages = build_chat_prompt(
        body.brief_context,
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
    body: BriefRegenerateRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    prompt = build_regeneration_prompt(
        body.section_title,
        body.current_content,
        body.judge_note,
        body.brief_context,
    )
    return await stream_anthropic(
        model_key="regenerate",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )


@router.post("/analyze")
async def analyze_documents(
    body: BriefAnalyzeRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    if not body.documents:
        raise HTTPException(status_code=400, detail="No documents provided")

    prompt = build_analysis_prompt(body.documents)
    client = get_client()
    model = settings.ai_models.get("analyze", "claude-sonnet-4-20250514")

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text_block = next((b for b in message.content if b.type == "text"), None)
    if not text_block:
        raise HTTPException(status_code=500, detail="No text response from AI")

    json_text = text_block.text.strip()
    if json_text.startswith("```"):
        json_text = re.sub(r"^```(?:json)?\n?", "", json_text)
        json_text = re.sub(r"\n?```$", "", json_text)

    extracted = json.loads(json_text)

    return _format_extracted_data(extracted, body.documents)


@router.post("/analyze-chunk")
async def analyze_chunk(
    body: BriefAnalyzeChunkRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    if not body.documents:
        raise HTTPException(status_code=400, detail="No documents provided")

    prompt = build_analysis_prompt(body.documents, body.chunk_index, body.total_chunks)
    client = get_client()
    model = settings.ai_models.get("analyze", "claude-sonnet-4-20250514")

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text_block = next((b for b in message.content if b.type == "text"), None)
    if not text_block:
        raise HTTPException(status_code=500, detail="No text response from AI")

    json_text = text_block.text.strip()
    if json_text.startswith("```"):
        json_text = re.sub(r"^```(?:json)?\n?", "", json_text)
        json_text = re.sub(r"\n?```$", "", json_text)

    extracted = json.loads(json_text)

    doc_prefix = f"chunk{body.chunk_index or 0}-"
    return _format_extracted_data(extracted, body.documents, doc_prefix)


@router.post("/precedents")
async def find_precedents(
    body: BriefPrecedentsRequest,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    from app.rag.service import search as rag_search

    extracted = body.extracted_data

    # Build search query from extracted data
    search_terms: list[str] = []
    for issue in extracted.get("legalIssues", []):
        if isinstance(issue, dict):
            search_terms.append(issue.get("content", ""))
    for statute in extracted.get("statutes", []):
        if isinstance(statute, dict):
            search_terms.append(statute.get("name", ""))
            search_terms.extend(statute.get("provisions", []))
    for arg in extracted.get("arguments", []):
        if isinstance(arg, dict):
            search_terms.extend(arg.get("supportingCitations", []))
    court_info = extracted.get("courtInfo")
    if isinstance(court_info, dict) and court_info.get("caseType"):
        search_terms.append(court_info["caseType"])

    rag_query = " ".join(search_terms[:10])
    search_results = await rag_search({"query": rag_query, "limit": 15})

    search_mapped = []
    for r in search_results:
        j = r.get("judgment", r)
        search_mapped.append({
            "id": j.get("id", ""),
            "caseName": j.get("caseName", j.get("case_name", "")),
            "citation": j.get("citation", ""),
            "court": j.get("court", ""),
            "year": j.get("year"),
            "legalAreas": j.get("legalAreas", j.get("legal_areas", [])),
            "keywords": j.get("keywords", []),
            "headnotes": j.get("headnotes", []),
            "summary": j.get("summary", ""),
            "ratio": j.get("ratio", ""),
        })

    # Re-rank with Claude
    legal_issues = [i.get("content", "") for i in extracted.get("legalIssues", []) if isinstance(i, dict)]
    statutes = [
        f"{s.get('name', '')} {', '.join(s.get('provisions', []))}"
        for s in extracted.get("statutes", []) if isinstance(s, dict)
    ]
    case_type = ""
    if isinstance(court_info, dict):
        case_type = court_info.get("caseType", "General")

    ranking_prompt = build_ranking_prompt(
        {"legalIssues": legal_issues, "statutes": statutes, "caseType": case_type},
        search_mapped,
    )

    client = get_client()
    model = settings.ai_models.get("rank_precedents", "claude-sonnet-4-20250514")
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": ranking_prompt}],
    )

    text_block = next((b for b in message.content if b.type == "text"), None)
    rankings: list[dict] = []

    if text_block:
        json_text = text_block.text.strip()
        if json_text.startswith("```"):
            json_text = re.sub(r"^```(?:json)?\n?", "", json_text)
            json_text = re.sub(r"\n?```$", "", json_text)
        try:
            rankings = json.loads(json_text)
        except (json.JSONDecodeError, ValueError):
            rankings = [
                {
                    "id": r["id"],
                    "relevanceScore": max(90 - i * 5, 40),
                    "matchedKeywords": [],
                    "matchedAreas": r.get("legalAreas", []),
                    "explanation": "Matched via full-text search",
                }
                for i, r in enumerate(search_mapped)
            ]

    # Build final results
    results = []
    for rank in rankings:
        if rank.get("relevanceScore", 0) <= 30:
            continue
        db_row = next((r for r in search_mapped if r["id"] == rank.get("id")), None)
        if not db_row:
            continue
        results.append({
            "precedent": {
                "id": db_row["id"],
                "caseName": db_row["caseName"],
                "citation": db_row["citation"],
                "court": db_row["court"],
                "year": db_row["year"],
                "legalAreas": db_row["legalAreas"],
                "keywords": db_row["keywords"],
                "headnotes": db_row["headnotes"],
                "summary": db_row["summary"],
                "ratio": db_row["ratio"],
            },
            "relevanceScore": rank["relevanceScore"],
            "matchedKeywords": rank.get("matchedKeywords", []),
            "matchedAreas": rank.get("matchedAreas", []),
        })
        if len(results) >= 10:
            break

    return results


# --------------- Helpers ---------------


def _format_extracted_data(extracted: dict, documents: list[dict], doc_prefix: str = "") -> dict:
    """Add empty sources arrays and rawDocuments to match ExtractedCaseData shape."""
    return {
        "courtInfo": {**extracted["courtInfo"], "sources": []} if extracted.get("courtInfo") else None,
        "parties": [{**p, "sources": []} for p in (extracted.get("parties") or [])],
        "facts": [{**f, "sources": []} for f in (extracted.get("facts") or [])],
        "legalIssues": [{**i, "sources": []} for i in (extracted.get("legalIssues") or [])],
        "statutes": [{**s, "sources": []} for s in (extracted.get("statutes") or [])],
        "arguments": [{**a, "sources": []} for a in (extracted.get("arguments") or [])],
        "rawDocuments": [
            {
                "id": f"doc-{doc_prefix}{idx}",
                "fileName": d.get("fileName", ""),
                "documentType": "Other",
                "totalPages": 0,
            }
            for idx, d in enumerate(documents)
        ],
    }
