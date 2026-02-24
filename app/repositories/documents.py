import json

from app.repositories.base import fetch_one, fetch_all, execute


def _map_doc(row) -> dict:
    meta = row.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "title": row["title"],
        "file_name": row["file_name"],
        "file_type": row["file_type"],
        "file_size": int(row["file_size"] or 0),
        "page_count": row.get("page_count") or 0,
        "document_type": row.get("document_type") or "Other",
        "blob_url": row["blob_url"],
        "blob_pathname": row["blob_pathname"],
        "brief_id": row.get("brief_id"),
        "judgment_id": row.get("judgment_id"),
        "metadata": meta or {},
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def list_documents(user_id: str, document_type: str | None = None, search: str | None = None) -> list[dict]:
    query = "SELECT * FROM documents WHERE user_id = $1"
    params: list = [user_id]
    idx = 2

    if document_type and document_type != "all":
        query += f" AND document_type = ${idx}"
        params.append(document_type)
        idx += 1

    if search and search.strip():
        query += f" AND (title ILIKE ${idx} OR file_name ILIKE ${idx})"
        params.append(f"%{search.strip()}%")
        idx += 1

    query += " ORDER BY created_at DESC"
    rows = await fetch_all(query, *params)
    return [_map_doc(r) for r in rows]


async def get_document(doc_id: str, user_id: str) -> dict | None:
    row = await fetch_one("SELECT * FROM documents WHERE id = $1 AND user_id = $2", doc_id, user_id)
    return _map_doc(row) if row else None


async def create_document(user_id: str, data: dict) -> str:
    row = await fetch_one(
        """INSERT INTO documents (user_id, title, file_name, file_type, file_size, page_count, document_type, blob_url, blob_pathname, brief_id, judgment_id)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
           RETURNING id""",
        user_id,
        data["title"],
        data["file_name"],
        data["file_type"],
        data["file_size"],
        data.get("page_count", 0),
        data.get("document_type", "Other"),
        data["blob_url"],
        data["blob_pathname"],
        data.get("brief_id"),
        data.get("judgment_id"),
    )
    return str(row["id"])


async def delete_document(doc_id: str, user_id: str) -> dict | None:
    row = await fetch_one(
        "DELETE FROM documents WHERE id = $1 AND user_id = $2 RETURNING blob_url",
        doc_id, user_id,
    )
    if not row:
        return None
    return {"blob_url": row["blob_url"]}


async def link_document(doc_id: str, user_id: str, brief_id: str | None = None, judgment_id: str | None = None) -> None:
    if brief_id is not None:
        await execute(
            "UPDATE documents SET brief_id = $1, updated_at = now() WHERE id = $2 AND user_id = $3",
            brief_id or None, doc_id, user_id,
        )
    if judgment_id is not None:
        await execute(
            "UPDATE documents SET judgment_id = $1, updated_at = now() WHERE id = $2 AND user_id = $3",
            judgment_id or None, doc_id, user_id,
        )
