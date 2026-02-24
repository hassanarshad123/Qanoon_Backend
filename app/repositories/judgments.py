import json

from app.repositories.base import fetch_one, fetch_all, execute


def _pj(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return val if val is not None else []


async def create_judgment(user_id: str, data: dict) -> str:
    row = await fetch_one(
        """INSERT INTO judgments (user_id, brief_id, case_title, case_number, court, status, case_data, rag_results)
           VALUES ($1, $2, $3, $4, $5, 'draft', $6, $7) RETURNING id""",
        user_id,
        data.get("brief_id"),
        data["case_title"],
        data.get("case_number"),
        data.get("court"),
        json.dumps(data.get("case_data") or {}),
        json.dumps(data.get("rag_results", [])),
    )
    jid = str(row["id"])

    for i, s in enumerate(data.get("sections", [])):
        await execute(
            "INSERT INTO judgment_sections (judgment_id, section_key, title, content, sort_order) VALUES ($1, $2, $3, $4, $5)",
            jid, s.get("section_key", f"section_{i}"), s.get("title", ""), s.get("content", ""), i,
        )

    return jid


async def get_judgment(jid: str, user_id: str) -> dict | None:
    row = await fetch_one("SELECT * FROM judgments WHERE id = $1 AND user_id = $2", jid, user_id)
    if not row:
        return None

    sections = await fetch_all("SELECT * FROM judgment_sections WHERE judgment_id = $1 ORDER BY sort_order", jid)
    convs = await fetch_all("SELECT * FROM judgment_conversations WHERE judgment_id = $1 ORDER BY created_at", jid)

    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "brief_id": row.get("brief_id"),
        "case_title": row["case_title"],
        "case_number": row.get("case_number"),
        "court": row.get("court"),
        "status": row["status"],
        "case_data": _pj(row.get("case_data")),
        "rag_results": _pj(row.get("rag_results")),
        "sections": [
            {
                "id": str(s["id"]),
                "section_key": s["section_key"],
                "title": s["title"],
                "content": s["content"],
                "sort_order": s["sort_order"],
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
                "citations": _pj(c.get("citations")),
                "created_at": c["created_at"].isoformat(),
            }
            for c in convs
        ],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def list_judgments(user_id: str) -> list[dict]:
    rows = await fetch_all(
        """SELECT j.id, j.case_title, j.case_number, j.court, j.status, j.created_at,
              (SELECT count(*) FROM judgment_sections WHERE judgment_id = j.id) as section_count
           FROM judgments j WHERE j.user_id = $1 ORDER BY j.created_at DESC""",
        user_id,
    )
    return [
        {
            "id": str(r["id"]),
            "case_title": r["case_title"],
            "case_number": r.get("case_number"),
            "court": r.get("court"),
            "status": r["status"],
            "section_count": int(r["section_count"] or 0),
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


async def update_section_content(section_id: str, user_id: str, content: str, increment: bool) -> None:
    check = await fetch_one(
        "SELECT j.id FROM judgment_sections js JOIN judgments j ON j.id = js.judgment_id WHERE js.id = $1 AND j.user_id = $2",
        section_id, user_id,
    )
    if not check:
        raise ValueError("Not found")

    if increment:
        await execute(
            "UPDATE judgment_sections SET content = $1, regeneration_count = regeneration_count + 1, review_status = 'pending_review', updated_at = now() WHERE id = $2",
            content, section_id,
        )
    else:
        await execute("UPDATE judgment_sections SET content = $1, updated_at = now() WHERE id = $2", content, section_id)


async def update_section_review(section_id: str, user_id: str, status: str, flag_note: str | None) -> None:
    check = await fetch_one(
        "SELECT j.id FROM judgment_sections js JOIN judgments j ON j.id = js.judgment_id WHERE js.id = $1 AND j.user_id = $2",
        section_id, user_id,
    )
    if not check:
        raise ValueError("Not found")

    await execute(
        "UPDATE judgment_sections SET review_status = $1, flag_note = $2, updated_at = now() WHERE id = $3",
        status, flag_note, section_id,
    )


async def save_chat(jid: str, user_id: str, role: str, content: str, citations: list) -> str:
    check = await fetch_one("SELECT id FROM judgments WHERE id = $1 AND user_id = $2", jid, user_id)
    if not check:
        raise ValueError("Not found")

    row = await fetch_one(
        "INSERT INTO judgment_conversations (judgment_id, role, content, citations) VALUES ($1, $2, $3, $4) RETURNING id",
        jid, role, content, json.dumps(citations),
    )
    return str(row["id"])


async def update_status(jid: str, user_id: str, status: str) -> None:
    await execute("UPDATE judgments SET status = $1, updated_at = now() WHERE id = $2 AND user_id = $3", status, jid, user_id)


async def delete_judgment(jid: str, user_id: str) -> None:
    await execute("DELETE FROM judgments WHERE id = $1 AND user_id = $2", jid, user_id)
