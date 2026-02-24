import json

from app.repositories.base import fetch_all, execute


async def log_activity(
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    entity_title: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        await execute(
            """INSERT INTO activity_log (user_id, action, entity_type, entity_id, entity_title, metadata)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            user_id, action, entity_type, entity_id, entity_title,
            json.dumps(metadata or {}),
        )
    except Exception:
        # Non-critical — don't break the main operation
        pass


async def get_recent_activity(user_id: str, limit: int = 20) -> list[dict]:
    rows = await fetch_all(
        "SELECT * FROM activity_log WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
        user_id, limit,
    )
    result = []
    for row in rows:
        meta = row["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        result.append({
            "id": str(row["id"]),
            "action": row["action"],
            "entity_type": row["entity_type"],
            "entity_id": row.get("entity_id"),
            "entity_title": row.get("entity_title"),
            "metadata": meta or {},
            "created_at": row["created_at"].isoformat(),
        })
    return result
