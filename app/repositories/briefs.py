import json
import logging

from app.repositories.base import fetch_one, fetch_all, execute

logger = logging.getLogger("qanoonai")


def _parse_json(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse JSON in briefs repo: %.100s", val)
            return []
    return val if val is not None else []


async def save_brief(user_id: str, data: dict) -> str:
    sections = data.get("sections", [])
    row = await fetch_one(
        """INSERT INTO briefs (case_title, case_number, court, status, extracted_data, uploaded_documents, rag_results, review_progress, user_id)
           VALUES ($1, $2, $3, 'in_review', $4, $5, $6, $7, $8)
           RETURNING id""",
        data["case_title"],
        data.get("case_number"),
        data.get("court"),
        json.dumps(data.get("extracted_data") or {}),
        json.dumps(data.get("uploaded_documents", [])),
        json.dumps(data.get("rag_results", [])),
        json.dumps({"total": len(sections), "approved": 0, "flagged": 0}),
        user_id,
    )
    brief_id = str(row["id"])

    for i, s in enumerate(sections):
        await execute(
            """INSERT INTO brief_sections (brief_id, section_key, title, content, sources, review_status, sort_order)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            brief_id,
            s.get("id", s.get("section_key", f"section_{i}")),
            s.get("title", ""),
            s.get("content", ""),
            json.dumps(s.get("sources", [])),
            s.get("review_status", "pending_review"),
            i,
        )

    return brief_id


async def get_brief(brief_id: str, user_id: str) -> dict | None:
    row = await fetch_one("SELECT * FROM briefs WHERE id = $1 AND user_id = $2", brief_id, user_id)
    if not row:
        return None

    sections = await fetch_all(
        "SELECT * FROM brief_sections WHERE brief_id = $1 ORDER BY sort_order", brief_id
    )
    conversations = await fetch_all(
        "SELECT * FROM brief_conversations WHERE brief_id = $1 ORDER BY created_at", brief_id
    )

    return {
        "id": str(row["id"]),
        "case_id": str(row["id"]),
        "case_title": row["case_title"],
        "case_number": row.get("case_number"),
        "court": row.get("court"),
        "status": row["status"],
        "extracted_data": _parse_json(row.get("extracted_data")),
        "uploaded_documents": _parse_json(row.get("uploaded_documents")),
        "rag_results": _parse_json(row.get("rag_results")),
        "review_progress": _parse_json(row.get("review_progress")),
        "sections": [
            {
                "id": str(s["id"]),
                "title": s["title"],
                "content": s["content"],
                "sources": _parse_json(s.get("sources")),
                "review_status": s.get("review_status", "pending_review"),
                "flag_note": s.get("flag_note"),
                "regeneration_count": s.get("regeneration_count", 0),
            }
            for s in sections
        ],
        "conversation": [
            {
                "id": str(c["id"]),
                "role": c["role"],
                "content": c["content"],
                "citations": _parse_json(c.get("citations")),
                "created_at": c["created_at"].isoformat(),
            }
            for c in conversations
        ],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def list_briefs(user_id: str) -> list[dict]:
    rows = await fetch_all(
        """SELECT b.*,
              (SELECT json_agg(json_build_object(
                 'id', s.id, 'title', s.title,
                 'content', substring(s.content from 1 for 200),
                 'sources', s.sources,
                 'review_status', s.review_status,
                 'flag_note', s.flag_note,
                 'regeneration_count', s.regeneration_count
               ) ORDER BY s.sort_order) FROM brief_sections s WHERE s.brief_id = b.id) as sections
           FROM briefs b WHERE b.user_id = $1 ORDER BY b.created_at DESC""",
        user_id,
    )

    result = []
    for row in rows:
        secs = _parse_json(row.get("sections")) or []
        result.append({
            "id": str(row["id"]),
            "case_id": str(row["id"]),
            "case_title": row["case_title"],
            "status": row["status"],
            "review_progress": _parse_json(row.get("review_progress")),
            "sections": [
                {
                    "id": str(s.get("id", "")),
                    "title": s.get("title", ""),
                    "content": s.get("content", ""),
                    "sources": _parse_json(s.get("sources")),
                    "review_status": s.get("review_status", "pending_review"),
                    "flag_note": s.get("flag_note"),
                    "regeneration_count": s.get("regeneration_count", 0),
                }
                for s in secs
            ],
            "created_at": row["created_at"].isoformat(),
        })
    return result


async def update_section_review(section_id: str, user_id: str, status: str, flag_note: str | None) -> None:
    check = await fetch_one(
        "SELECT b.id as brief_id FROM brief_sections bs JOIN briefs b ON b.id = bs.brief_id WHERE bs.id = $1 AND b.user_id = $2",
        section_id, user_id,
    )
    if not check:
        raise ValueError("Not found")

    await execute(
        "UPDATE brief_sections SET review_status = $1, flag_note = $2, updated_at = now() WHERE id = $3",
        status, flag_note, section_id,
    )

    brief_id = str(check["brief_id"])
    await execute(
        """UPDATE briefs SET review_progress = (
             SELECT json_build_object(
               'total', count(*),
               'approved', count(*) FILTER (WHERE review_status = 'approved'),
               'flagged', count(*) FILTER (WHERE review_status = 'flagged')
             ) FROM brief_sections WHERE brief_id = $1
           ), updated_at = now() WHERE id = $1""",
        brief_id,
    )


async def update_section_content(section_id: str, user_id: str, content: str, increment: bool) -> None:
    check = await fetch_one(
        "SELECT b.id FROM brief_sections bs JOIN briefs b ON b.id = bs.brief_id WHERE bs.id = $1 AND b.user_id = $2",
        section_id, user_id,
    )
    if not check:
        raise ValueError("Not found")

    if increment:
        await execute(
            "UPDATE brief_sections SET content = $1, regeneration_count = regeneration_count + 1, review_status = 'pending_review', updated_at = now() WHERE id = $2",
            content, section_id,
        )
    else:
        await execute(
            "UPDATE brief_sections SET content = $1, updated_at = now() WHERE id = $2",
            content, section_id,
        )


async def save_chat_message(brief_id: str, user_id: str, role: str, content: str, citations: list) -> str:
    check = await fetch_one("SELECT id FROM briefs WHERE id = $1 AND user_id = $2", brief_id, user_id)
    if not check:
        raise ValueError("Not found")

    row = await fetch_one(
        "INSERT INTO brief_conversations (brief_id, role, content, citations) VALUES ($1, $2, $3, $4) RETURNING id",
        brief_id, role, content, json.dumps(citations),
    )
    return str(row["id"])


async def update_brief_status(brief_id: str, user_id: str, status: str) -> None:
    await execute(
        "UPDATE briefs SET status = $1, updated_at = now() WHERE id = $2 AND user_id = $3",
        status, brief_id, user_id,
    )


async def delete_brief(brief_id: str, user_id: str) -> None:
    await execute("DELETE FROM briefs WHERE id = $1 AND user_id = $2", brief_id, user_id)
