import json

from app.repositories.base import fetch_one, fetch_all, execute


def _parse_tag_ids(val) -> list[str]:
    if isinstance(val, list):
        return [str(x) for x in val if x is not None]
    return []


def _map_note(row) -> dict:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "content": row["content"],
        "folder": row["folder"],
        "tags": _parse_tag_ids(row.get("tag_ids")),
        "source_id": row.get("source_id"),
        "source_type": row.get("source_type"),
        "source_label": row.get("source_label"),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def create_note(user_id: str, data: dict) -> str:
    row = await fetch_one(
        """INSERT INTO notes (title, content, folder, source_id, source_type, source_label, user_id)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING id""",
        data.get("title", "Untitled Note"),
        data.get("content", ""),
        data.get("folder", "General"),
        data.get("source_id"),
        data.get("source_type"),
        data.get("source_label"),
        user_id,
    )
    note_id = str(row["id"])

    tags = data.get("tags", [])
    for tag_id in tags:
        await execute(
            "INSERT INTO note_tags (note_id, tag_id) VALUES ($1, $2)",
            note_id, tag_id,
        )

    return note_id


async def get_note(note_id: str, user_id: str) -> dict | None:
    row = await fetch_one(
        """SELECT n.*, array_agg(nt.tag_id) FILTER (WHERE nt.tag_id IS NOT NULL) as tag_ids
           FROM notes n
           LEFT JOIN note_tags nt ON n.id = nt.note_id
           WHERE n.id = $1 AND n.user_id = $2
           GROUP BY n.id""",
        note_id, user_id,
    )
    return _map_note(row) if row else None


async def list_notes(user_id: str) -> list[dict]:
    rows = await fetch_all(
        """SELECT n.*, array_agg(nt.tag_id) FILTER (WHERE nt.tag_id IS NOT NULL) as tag_ids
           FROM notes n
           LEFT JOIN note_tags nt ON n.id = nt.note_id
           WHERE n.user_id = $1
           GROUP BY n.id
           ORDER BY n.updated_at DESC""",
        user_id,
    )
    return [_map_note(r) for r in rows]


async def update_note_content(note_id: str, user_id: str, content: str) -> dict:
    row = await fetch_one(
        """UPDATE notes SET content = $1, updated_at = now()
           WHERE id = $2 AND user_id = $3
           RETURNING updated_at""",
        content, note_id, user_id,
    )
    if not row:
        raise ValueError("Note not found")
    return {"updated_at": row["updated_at"].isoformat()}


async def update_note_title(note_id: str, user_id: str, title: str) -> dict:
    row = await fetch_one(
        """UPDATE notes SET title = $1, updated_at = now()
           WHERE id = $2 AND user_id = $3
           RETURNING updated_at""",
        title, note_id, user_id,
    )
    if not row:
        raise ValueError("Note not found")
    return {"updated_at": row["updated_at"].isoformat()}


async def update_note_metadata(note_id: str, user_id: str, folder: str | None, tags: list[str] | None) -> None:
    if folder:
        await execute(
            "UPDATE notes SET folder = $1, updated_at = now() WHERE id = $2 AND user_id = $3",
            folder, note_id, user_id,
        )

    if tags is not None:
        # Verify ownership
        row = await fetch_one("SELECT id FROM notes WHERE id = $1 AND user_id = $2", note_id, user_id)
        if not row:
            raise ValueError("Note not found")

        await execute("DELETE FROM note_tags WHERE note_id = $1", note_id)
        for tag_id in tags:
            await execute("INSERT INTO note_tags (note_id, tag_id) VALUES ($1, $2)", note_id, tag_id)


async def delete_note(note_id: str, user_id: str) -> None:
    await execute("DELETE FROM notes WHERE id = $1 AND user_id = $2", note_id, user_id)


async def list_folders(user_id: str) -> list[dict]:
    rows = await fetch_all(
        """SELECT f.id, f.name, f.sort_order, COUNT(n.id) as count
           FROM folders f
           LEFT JOIN notes n ON n.folder = f.name AND n.user_id = $1
           WHERE f.user_id = $1 OR f.user_id IS NULL
           GROUP BY f.id, f.name, f.sort_order
           ORDER BY f.sort_order, f.created_at""",
        user_id,
    )
    return [{"id": str(r["id"]), "name": r["name"], "count": int(r["count"] or 0)} for r in rows]


async def create_folder(user_id: str, name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Folder name cannot be empty")

    max_row = await fetch_one(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 as next_order FROM folders WHERE user_id = $1 OR user_id IS NULL",
        user_id,
    )
    next_order = max_row["next_order"] if max_row else 1

    row = await fetch_one(
        "INSERT INTO folders (name, sort_order, user_id) VALUES ($1, $2, $3) RETURNING id",
        name, next_order, user_id,
    )
    return str(row["id"])


async def delete_folder(user_id: str, folder_name: str) -> None:
    if folder_name == "General":
        raise ValueError("Cannot delete the General folder")

    await execute(
        "UPDATE notes SET folder = 'General', updated_at = now() WHERE folder = $1 AND user_id = $2",
        folder_name, user_id,
    )
    await execute(
        "DELETE FROM folders WHERE name = $1 AND (user_id = $2 OR user_id IS NULL)",
        folder_name, user_id,
    )


async def get_tags() -> list[dict]:
    rows = await fetch_all("SELECT id, name, color FROM tags ORDER BY name")
    return [{"id": str(r["id"]), "name": r["name"], "color": r["color"]} for r in rows]
