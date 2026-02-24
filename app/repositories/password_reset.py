import uuid
from datetime import datetime, timedelta, timezone

from app.repositories.base import fetch_one, execute


async def create_token(user_id: str) -> str:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    await execute(
        """INSERT INTO password_reset_tokens (user_id, token, expires_at)
           VALUES ($1, $2, $3)""",
        user_id, token, expires_at,
    )
    return token


async def validate_token(token: str) -> dict | None:
    row = await fetch_one(
        """SELECT prt.id, prt.user_id, prt.expires_at, prt.used, u.email
           FROM password_reset_tokens prt
           JOIN users u ON u.id = prt.user_id
           WHERE prt.token = $1""",
        token,
    )
    if not row:
        return None
    if row["used"]:
        return None
    if row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    return {"id": str(row["id"]), "user_id": str(row["user_id"]), "email": row["email"]}


async def consume_token(token: str) -> None:
    await execute(
        "UPDATE password_reset_tokens SET used = true WHERE token = $1",
        token,
    )
