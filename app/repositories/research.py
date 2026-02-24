import json
import logging

from app.repositories.base import fetch_one, fetch_all, execute

logger = logging.getLogger("qanoonai")


def _pj(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse JSON in research repo: %.100s", val)
            return []
    return val if val is not None else []


def _map_conv(r) -> dict:
    return {
        "id": str(r["id"]),
        "title": r["title"],
        "case_id": r.get("case_id"),
        "legal_areas": _pj(r.get("legal_areas")),
        "status": r.get("status", "active"),
        "pinned": r.get("pinned", False),
        "mode": r.get("mode", "general"),
        "message_count": int(r.get("message_count", 0)),
        "last_message_preview": r.get("first_message"),
        "created_at": r["created_at"].isoformat(),
        "updated_at": r["updated_at"].isoformat(),
    }


async def create_conversation(user_id: str, title: str, case_id: str | None, mode: str) -> str:
    row = await fetch_one(
        "INSERT INTO research_conversations (title, case_id, mode, user_id) VALUES ($1, $2, $3, $4) RETURNING id",
        title, case_id, mode, user_id,
    )
    return str(row["id"])


async def get_conversation(conv_id: str, user_id: str) -> dict | None:
    row = await fetch_one(
        """SELECT rc.*,
              (SELECT count(*) FROM research_messages WHERE conversation_id = rc.id) AS message_count,
              (SELECT content FROM research_messages WHERE conversation_id = rc.id ORDER BY created_at LIMIT 1) AS first_message
           FROM research_conversations rc WHERE rc.id = $1 AND rc.user_id = $2""",
        conv_id, user_id,
    )
    return _map_conv(row) if row else None


async def list_conversations(user_id: str, search: str | None = None, limit: int = 50) -> list[dict]:
    if search and search.strip():
        rows = await fetch_all(
            """SELECT rc.*,
                  (SELECT count(*) FROM research_messages WHERE conversation_id = rc.id) AS message_count,
                  (SELECT content FROM research_messages WHERE conversation_id = rc.id AND role = 'user' ORDER BY created_at LIMIT 1) AS first_message
               FROM research_conversations rc
               WHERE rc.user_id = $1 AND (rc.title ILIKE $2 OR EXISTS (
                 SELECT 1 FROM research_messages rm WHERE rm.conversation_id = rc.id AND rm.content ILIKE $2
               ))
               ORDER BY rc.pinned DESC, rc.updated_at DESC LIMIT $3""",
            user_id, f"%{search.strip()}%", limit,
        )
    else:
        rows = await fetch_all(
            """SELECT rc.*,
                  (SELECT count(*) FROM research_messages WHERE conversation_id = rc.id) AS message_count,
                  (SELECT content FROM research_messages WHERE conversation_id = rc.id AND role = 'user' ORDER BY created_at LIMIT 1) AS first_message
               FROM research_conversations rc WHERE rc.user_id = $1
               ORDER BY rc.pinned DESC, rc.updated_at DESC LIMIT $2""",
            user_id, limit,
        )
    return [_map_conv(r) for r in rows]


async def delete_conversation(conv_id: str, user_id: str) -> None:
    await execute("DELETE FROM research_conversations WHERE id = $1 AND user_id = $2", conv_id, user_id)


async def toggle_pin(conv_id: str, user_id: str) -> bool:
    row = await fetch_one(
        "UPDATE research_conversations SET pinned = NOT pinned, updated_at = now() WHERE id = $1 AND user_id = $2 RETURNING pinned",
        conv_id, user_id,
    )
    return bool(row and row["pinned"])


async def update_meta(conv_id: str, user_id: str, legal_areas: list[str] | None, case_id: str | None) -> None:
    if legal_areas is not None:
        await execute(
            "UPDATE research_conversations SET legal_areas = $1, updated_at = now() WHERE id = $2 AND user_id = $3",
            json.dumps(legal_areas), conv_id, user_id,
        )
    if case_id is not None:
        await execute(
            "UPDATE research_conversations SET case_id = $1, updated_at = now() WHERE id = $2 AND user_id = $3",
            case_id, conv_id, user_id,
        )


async def get_messages(conv_id: str, user_id: str) -> list[dict]:
    # Verify conversation belongs to user before returning messages
    owner = await fetch_one(
        "SELECT id FROM research_conversations WHERE id = $1 AND user_id = $2",
        conv_id, user_id,
    )
    if not owner:
        return []

    rows = await fetch_all(
        "SELECT * FROM research_messages WHERE conversation_id = $1 ORDER BY created_at",
        conv_id,
    )
    return [
        {
            "id": str(r["id"]),
            "conversation_id": str(r["conversation_id"]),
            "role": r["role"],
            "content": r["content"],
            "structured_response": _pj(r.get("structured_response")),
            "citations": _pj(r.get("citations")),
            "rag_context": _pj(r.get("rag_context")) if r.get("rag_context") else None,
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


async def save_message(
    conversation_id: str,
    role: str,
    content: str,
    structured_response: dict | None = None,
    citations: list[dict] | None = None,
    rag_context: list[dict] | None = None,
) -> str:
    row = await fetch_one(
        """INSERT INTO research_messages (conversation_id, role, content, structured_response, citations, rag_context)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
        conversation_id,
        role,
        content,
        json.dumps(structured_response) if structured_response else None,
        json.dumps(citations) if citations else json.dumps([]),
        json.dumps(rag_context) if rag_context else None,
    )
    await execute("UPDATE research_conversations SET updated_at = now() WHERE id = $1", conversation_id)
    return str(row["id"])


async def update_title(conv_id: str, title: str) -> None:
    await execute(
        "UPDATE research_conversations SET title = $1, updated_at = now() WHERE id = $2",
        title, conv_id,
    )
