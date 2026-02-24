import json

from app.repositories.base import fetch_one, execute


async def submit_onboarding(
    role: str,
    email: str,
    data: dict,
    user_id: str | None = None,
) -> dict:
    """Submit onboarding data. Returns {"success": True/False, "error": ...}."""
    try:
        personal_info = data.get("personalInfo", {})
        full_name = personal_info.get("fullName")
        phone = personal_info.get("phone")

        await execute(
            """INSERT INTO onboarding_submissions (role, email, data, full_name, phone, user_id)
               VALUES ($1, $2, $3::jsonb, $4, $5, $6)
               ON CONFLICT (email) DO UPDATE SET
                 role = EXCLUDED.role,
                 data = EXCLUDED.data,
                 full_name = EXCLUDED.full_name,
                 phone = EXCLUDED.phone,
                 user_id = EXCLUDED.user_id,
                 updated_at = now()""",
            role, email, json.dumps(data), full_name, phone, user_id,
        )

        if user_id:
            await execute(
                "UPDATE users SET role = $1, onboarding_completed = true, updated_at = now() WHERE id = $2",
                role, user_id,
            )

            if role == "judge":
                court_info = data.get("courtInfo", {})
                await execute(
                    """INSERT INTO judge_profiles (user_id, full_name, email, phone, court_level, designation, province, city, court_name)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                       ON CONFLICT (user_id) DO UPDATE SET
                         full_name = COALESCE(EXCLUDED.full_name, judge_profiles.full_name),
                         email = COALESCE(EXCLUDED.email, judge_profiles.email),
                         phone = COALESCE(EXCLUDED.phone, judge_profiles.phone),
                         court_level = COALESCE(EXCLUDED.court_level, judge_profiles.court_level),
                         designation = COALESCE(EXCLUDED.designation, judge_profiles.designation),
                         province = COALESCE(EXCLUDED.province, judge_profiles.province),
                         city = COALESCE(EXCLUDED.city, judge_profiles.city),
                         court_name = COALESCE(EXCLUDED.court_name, judge_profiles.court_name),
                         updated_at = now()""",
                    user_id, full_name, email, phone,
                    court_info.get("courtLevel"),
                    court_info.get("designation"),
                    court_info.get("province"),
                    court_info.get("city"),
                    court_info.get("courtName"),
                )

            if role == "lawyer":
                pd = data.get("practiceDetails", {})
                loc = data.get("location", {})
                fi = data.get("firmInfo", {})
                practice_areas = pd.get("practiceAreas", []) if isinstance(pd.get("practiceAreas"), list) else []
                await execute(
                    """INSERT INTO lawyer_profiles (user_id, full_name, email, phone, bar_council_number, years_of_experience, practice_areas, province, city, primary_court, firm_type, firm_name)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                       ON CONFLICT (user_id) DO UPDATE SET
                         full_name = COALESCE(EXCLUDED.full_name, lawyer_profiles.full_name),
                         email = COALESCE(EXCLUDED.email, lawyer_profiles.email),
                         phone = COALESCE(EXCLUDED.phone, lawyer_profiles.phone),
                         bar_council_number = COALESCE(EXCLUDED.bar_council_number, lawyer_profiles.bar_council_number),
                         years_of_experience = COALESCE(EXCLUDED.years_of_experience, lawyer_profiles.years_of_experience),
                         practice_areas = COALESCE(EXCLUDED.practice_areas, lawyer_profiles.practice_areas),
                         province = COALESCE(EXCLUDED.province, lawyer_profiles.province),
                         city = COALESCE(EXCLUDED.city, lawyer_profiles.city),
                         primary_court = COALESCE(EXCLUDED.primary_court, lawyer_profiles.primary_court),
                         firm_type = COALESCE(EXCLUDED.firm_type, lawyer_profiles.firm_type),
                         firm_name = COALESCE(EXCLUDED.firm_name, lawyer_profiles.firm_name),
                         updated_at = now()""",
                    user_id, full_name, email, phone,
                    pd.get("barCouncilNumber"),
                    pd.get("yearsOfExperience"),
                    practice_areas,
                    loc.get("province"),
                    loc.get("city"),
                    loc.get("primaryCourt"),
                    fi.get("firmType"),
                    fi.get("firmName"),
                )

        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def submit_coming_soon(role: str, email: str) -> dict:
    try:
        await execute(
            """INSERT INTO coming_soon_signups (role, email)
               VALUES ($1, $2)
               ON CONFLICT (email, role) DO NOTHING""",
            role, email,
        )
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}
