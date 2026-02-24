import json
import logging

from app.repositories.base import fetch_one, fetch_all, execute

logger = logging.getLogger("qanoonai")


# ---------------------------------------------------------------------------
# Judge profiles
# ---------------------------------------------------------------------------

def _map_judge(row) -> dict:
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "full_name": row["full_name"],
        "email": row["email"],
        "phone": row["phone"],
        "court_level": row["court_level"],
        "designation": row["designation"],
        "province": row["province"],
        "city": row["city"],
        "court_name": row["court_name"],
        "tour_completed": row.get("tour_completed", False) or False,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def get_judge_profile(user_id: str) -> dict | None:
    row = await fetch_one("SELECT * FROM judge_profiles WHERE user_id = $1", user_id)
    return _map_judge(row) if row else None


async def update_judge_profile(user_id: str, data: dict) -> dict:
    row = await fetch_one(
        """UPDATE judge_profiles SET
              full_name = COALESCE($2, full_name),
              email = COALESCE($3, email),
              phone = COALESCE($4, phone),
              court_level = COALESCE($5, court_level),
              designation = COALESCE($6, designation),
              province = COALESCE($7, province),
              city = COALESCE($8, city),
              court_name = COALESCE($9, court_name),
              updated_at = now()
           WHERE user_id = $1
           RETURNING *""",
        user_id,
        data.get("full_name"),
        data.get("email"),
        data.get("phone"),
        data.get("court_level"),
        data.get("designation"),
        data.get("province"),
        data.get("city"),
        data.get("court_name"),
    )
    return _map_judge(row)


async def get_or_create_judge_profile(user_id: str) -> dict:
    existing = await get_judge_profile(user_id)
    if existing:
        return existing

    # Try onboarding data
    onboarding = await fetch_one(
        "SELECT data, full_name, email, phone FROM onboarding_submissions WHERE user_id = $1 LIMIT 1",
        user_id,
    )

    full_name = phone = email = court_level = designation = province = city = court_name = None

    if onboarding:
        full_name = onboarding["full_name"]
        email = onboarding["email"]
        phone = onboarding["phone"]
        raw = onboarding["data"]
        data = json.loads(raw) if isinstance(raw, str) else raw
        if data:
            pi = data.get("personalInfo", {})
            ci = data.get("courtInfo") or data.get("professionalInfo") or {}
            full_name = full_name or pi.get("fullName")
            phone = phone or pi.get("phone")
            court_level = ci.get("courtLevel") or ci.get("court_level")
            designation = ci.get("designation")
            province = ci.get("province")
            city = ci.get("city")
            court_name = ci.get("courtName") or ci.get("court_name")

    if not email or not full_name:
        user = await fetch_one("SELECT email, name FROM users WHERE id = $1", user_id)
        if user:
            email = email or user["email"]
            full_name = full_name or user["name"]

    row = await fetch_one(
        """INSERT INTO judge_profiles (user_id, full_name, email, phone, court_level, designation, province, city, court_name)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
           ON CONFLICT (user_id) DO UPDATE SET updated_at = now()
           RETURNING *""",
        user_id, full_name, email, phone, court_level, designation, province, city, court_name,
    )
    return _map_judge(row)


async def is_judge_tour_completed(user_id: str) -> bool:
    row = await fetch_one(
        "SELECT tour_completed FROM judge_profiles WHERE user_id = $1", user_id
    )
    return bool(row and row["tour_completed"])


async def mark_judge_tour_complete(user_id: str) -> None:
    await execute(
        "UPDATE judge_profiles SET tour_completed = true, updated_at = now() WHERE user_id = $1",
        user_id,
    )


# ---------------------------------------------------------------------------
# Lawyer profiles
# ---------------------------------------------------------------------------

def _parse_practice_areas(val) -> list[str]:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        trimmed = val.strip("{}").strip()
        return [s.strip().strip('"') for s in trimmed.split(",")] if trimmed else []
    return []


def _map_lawyer(row) -> dict:
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "full_name": row["full_name"],
        "email": row["email"],
        "phone": row["phone"],
        "bar_council_number": row["bar_council_number"],
        "years_of_experience": row["years_of_experience"],
        "practice_areas": _parse_practice_areas(row["practice_areas"]),
        "province": row["province"],
        "city": row["city"],
        "primary_court": row["primary_court"],
        "firm_type": row["firm_type"],
        "firm_name": row["firm_name"],
        "tour_completed": row.get("tour_completed", False) or False,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def get_lawyer_profile(user_id: str) -> dict | None:
    row = await fetch_one("SELECT * FROM lawyer_profiles WHERE user_id = $1", user_id)
    return _map_lawyer(row) if row else None


async def update_lawyer_profile(user_id: str, data: dict) -> dict:
    row = await fetch_one(
        """UPDATE lawyer_profiles SET
              full_name = COALESCE($2, full_name),
              email = COALESCE($3, email),
              phone = COALESCE($4, phone),
              bar_council_number = COALESCE($5, bar_council_number),
              years_of_experience = COALESCE($6, years_of_experience),
              practice_areas = COALESCE($7, practice_areas),
              province = COALESCE($8, province),
              city = COALESCE($9, city),
              primary_court = COALESCE($10, primary_court),
              firm_type = COALESCE($11, firm_type),
              firm_name = COALESCE($12, firm_name),
              updated_at = now()
           WHERE user_id = $1
           RETURNING *""",
        user_id,
        data.get("full_name"),
        data.get("email"),
        data.get("phone"),
        data.get("bar_council_number"),
        data.get("years_of_experience"),
        data.get("practice_areas"),
        data.get("province"),
        data.get("city"),
        data.get("primary_court"),
        data.get("firm_type"),
        data.get("firm_name"),
    )
    return _map_lawyer(row)


async def get_or_create_lawyer_profile(user_id: str) -> dict:
    existing = await get_lawyer_profile(user_id)
    if existing:
        return existing

    onboarding = await fetch_one(
        "SELECT data, full_name, email, phone FROM onboarding_submissions WHERE user_id = $1 LIMIT 1",
        user_id,
    )

    full_name = phone = email = bar_council_number = years_of_experience = None
    practice_areas: list[str] = []
    province = city = primary_court = firm_type = firm_name = None

    if onboarding:
        full_name = onboarding["full_name"]
        email = onboarding["email"]
        phone = onboarding["phone"]
        raw = onboarding["data"]
        data = json.loads(raw) if isinstance(raw, str) else raw
        if data:
            pi = data.get("personalInfo", {})
            pd = data.get("practiceDetails", {})
            loc = data.get("location", {})
            fi = data.get("firmInfo", {})
            full_name = full_name or pi.get("fullName")
            phone = phone or pi.get("phone")
            bar_council_number = pd.get("barCouncilNumber") or pd.get("bar_council_number")
            years_of_experience = pd.get("yearsOfExperience") or pd.get("years_of_experience")
            practice_areas = pd.get("practiceAreas", []) if isinstance(pd.get("practiceAreas"), list) else []
            province = loc.get("province")
            city = loc.get("city")
            primary_court = loc.get("primaryCourt") or loc.get("primary_court")
            firm_type = fi.get("firmType") or fi.get("firm_type")
            firm_name = fi.get("firmName") or fi.get("firm_name")

    if not email or not full_name:
        user = await fetch_one("SELECT email, name FROM users WHERE id = $1", user_id)
        if user:
            email = email or user["email"]
            full_name = full_name or user["name"]

    row = await fetch_one(
        """INSERT INTO lawyer_profiles (user_id, full_name, email, phone, bar_council_number, years_of_experience, practice_areas, province, city, primary_court, firm_type, firm_name)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
           ON CONFLICT (user_id) DO UPDATE SET updated_at = now()
           RETURNING *""",
        user_id, full_name, email, phone, bar_council_number, years_of_experience, practice_areas, province, city, primary_court, firm_type, firm_name,
    )
    return _map_lawyer(row)


# ---------------------------------------------------------------------------
# Lawyer tour state
# ---------------------------------------------------------------------------

def _parse_json(val) -> dict:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse JSON in profiles repo: %.100s", val)
            return {}
    if isinstance(val, dict):
        return val
    return {}


async def get_lawyer_tour_state(user_id: str) -> dict:
    row = await fetch_one(
        "SELECT tour_state FROM lawyer_profiles WHERE user_id = $1", user_id
    )
    if not row:
        return {}
    return _parse_json(row["tour_state"])


async def update_lawyer_tour_state(user_id: str, patch: dict) -> dict:
    current = await get_lawyer_tour_state(user_id)
    merged = {**current, **patch}
    await execute(
        "UPDATE lawyer_profiles SET tour_state = $2, updated_at = now() WHERE user_id = $1",
        user_id, json.dumps(merged),
    )
    return merged


async def reset_lawyer_tour(user_id: str) -> dict:
    await execute(
        "UPDATE lawyer_profiles SET tour_state = '{}', updated_at = now() WHERE user_id = $1",
        user_id,
    )
    return {}
