import json

from app.repositories.base import fetch_one, fetch_all, execute


async def get_stats() -> dict:
    total = await fetch_one("SELECT COUNT(*)::int AS count FROM users")
    active = await fetch_one("SELECT COUNT(*)::int AS count FROM users WHERE is_active = true")
    inactive = await fetch_one("SELECT COUNT(*)::int AS count FROM users WHERE is_active = false")
    week = await fetch_one("SELECT COUNT(*)::int AS count FROM users WHERE created_at >= now() - interval '7 days'")
    role_rows = await fetch_all(
        "SELECT COALESCE(role, 'unassigned') AS role, COUNT(*)::int AS count FROM users GROUP BY role ORDER BY count DESC"
    )

    return {
        "totalUsers": total["count"],
        "activeUsers": active["count"],
        "inactiveUsers": inactive["count"],
        "newThisWeek": week["count"],
        "byRole": [{"role": r["role"], "count": r["count"]} for r in role_rows],
    }


async def get_users(
    search: str | None = None,
    role_filter: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    conditions: list[str] = []
    params: list = []
    idx = 1

    if search and search.strip():
        conditions.append(f"(email ILIKE ${idx} OR name ILIKE ${idx})")
        params.append(f"%{search.strip()}%")
        idx += 1

    if role_filter and role_filter != "all":
        if role_filter == "unassigned":
            conditions.append("role IS NULL")
        else:
            conditions.append(f"role = ${idx}")
            params.append(role_filter)
            idx += 1

    if status_filter == "active":
        conditions.append("is_active = true")
    elif status_filter == "inactive":
        conditions.append("is_active = false")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size

    count_row = await fetch_one(
        f"SELECT COUNT(*)::int AS count FROM users {where}",
        *params,
    )
    total = count_row["count"]

    rows = await fetch_all(
        f"""SELECT id, email, name, role, onboarding_completed, is_active, created_at, updated_at
            FROM users {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}""",
        *params, page_size, offset,
    )

    import math
    return {
        "users": [
            {
                "id": str(r["id"]),
                "email": r["email"],
                "name": r.get("name"),
                "role": r.get("role"),
                "onboardingCompleted": r.get("onboarding_completed", False),
                "isActive": r.get("is_active", True),
                "createdAt": r["created_at"].isoformat() if r.get("created_at") else None,
                "updatedAt": r["updated_at"].isoformat() if r.get("updated_at") else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": math.ceil(total / page_size) if page_size > 0 else 0,
    }


async def get_user_detail(user_id: str) -> dict | None:
    user = await fetch_one(
        "SELECT id, email, name, role, onboarding_completed, is_active, created_at, updated_at FROM users WHERE id = $1",
        user_id,
    )
    if not user:
        return None

    onboarding = await fetch_one(
        "SELECT role, data, full_name, phone, created_at, updated_at FROM onboarding_submissions WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
        user_id,
    )

    result = {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user.get("name"),
        "role": user.get("role"),
        "onboardingCompleted": user.get("onboarding_completed", False),
        "isActive": user.get("is_active", True),
        "createdAt": user["created_at"].isoformat() if user.get("created_at") else None,
        "updatedAt": user["updated_at"].isoformat() if user.get("updated_at") else None,
        "onboardingData": None,
    }

    if onboarding:
        data = onboarding.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                pass
        result["onboardingData"] = {
            "role": onboarding.get("role"),
            "data": data,
            "fullName": onboarding.get("full_name"),
            "phone": onboarding.get("phone"),
        }

    return result


async def toggle_user_status(user_id: str, is_active: bool) -> None:
    await execute(
        "UPDATE users SET is_active = $1, updated_at = now() WHERE id = $2",
        is_active, user_id,
    )


async def change_user_role(user_id: str, new_role: str) -> None:
    valid_roles = ["lawyer", "judge", "law_student", "common_person", "admin"]
    if new_role not in valid_roles:
        raise ValueError(f"Invalid role: {new_role}")
    await execute(
        "UPDATE users SET role = $1, updated_at = now() WHERE id = $2",
        new_role, user_id,
    )
