import bcrypt

from app.repositories.base import fetch_one, execute


async def create_user(
    email: str, password: str, name: str, role: str | None = None
) -> dict:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()

    if role:
        row = await fetch_one(
            """INSERT INTO users (email, password_hash, name, role)
               VALUES ($1, $2, $3, $4)
               RETURNING id, email, name, role, onboarding_completed, is_active, created_at""",
            email, password_hash, name, role,
        )
    else:
        row = await fetch_one(
            """INSERT INTO users (email, password_hash, name)
               VALUES ($1, $2, $3)
               RETURNING id, email, name, role, onboarding_completed, is_active, created_at""",
            email, password_hash, name,
        )
    return dict(row) if row else {}


async def get_user_by_email(email: str) -> dict | None:
    row = await fetch_one(
        """SELECT id, email, password_hash, name, role, onboarding_completed, is_active, created_at, updated_at
           FROM users WHERE email = $1""",
        email,
    )
    return dict(row) if row else None


async def get_user_by_id(user_id: str) -> dict | None:
    row = await fetch_one(
        """SELECT id, email, name, role, onboarding_completed, is_active, created_at, updated_at
           FROM users WHERE id = $1""",
        user_id,
    )
    return dict(row) if row else None


async def update_user_password(user_id: str, new_password_hash: str) -> None:
    await execute(
        "UPDATE users SET password_hash = $1, updated_at = now() WHERE id = $2",
        new_password_hash, user_id,
    )


async def complete_onboarding(user_id: str, role: str) -> None:
    await execute(
        "UPDATE users SET role = $1, onboarding_completed = true, updated_at = now() WHERE id = $2",
        role, user_id,
    )
