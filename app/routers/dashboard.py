from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import SessionUser, get_current_user
from app.repositories import profiles as profiles_repo
from app.repositories import activity as activity_repo
from app.repositories.base import fetch_one, fetch_all

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/judge")
async def judge_dashboard(user: Annotated[SessionUser, Depends(get_current_user)]):
    uid = user.id

    profile = await profiles_repo.get_or_create_judge_profile(uid)
    recent_activity = await activity_repo.get_recent_activity(uid, 10)

    # Stats
    brief_row = await fetch_one("SELECT COUNT(*) as count FROM briefs WHERE user_id = $1", uid)
    research_row = await fetch_one("SELECT COUNT(*) as count FROM research_conversations WHERE user_id = $1", uid)
    note_row = await fetch_one("SELECT COUNT(*) as count FROM notes WHERE user_id = $1", uid)

    judgment_count = 0
    doc_count = 0
    try:
        j_row = await fetch_one("SELECT COUNT(*) as count FROM judgments WHERE user_id = $1", uid)
        judgment_count = int(j_row["count"]) if j_row else 0
    except Exception:
        pass
    try:
        d_row = await fetch_one("SELECT COUNT(*) as count FROM documents WHERE user_id = $1", uid)
        doc_count = int(d_row["count"]) if d_row else 0
    except Exception:
        pass

    # Recent work
    recent_briefs = await fetch_all(
        "SELECT id, case_title, status, created_at FROM briefs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 5",
        uid,
    )

    return {
        "profile": profile,
        "stats": {
            "total_briefs": int(brief_row["count"]) if brief_row else 0,
            "total_research": int(research_row["count"]) if research_row else 0,
            "total_notes": int(note_row["count"]) if note_row else 0,
            "total_judgments": judgment_count,
            "total_documents": doc_count,
        },
        "recent_activity": recent_activity,
        "recent_work": [
            {
                "id": str(r["id"]),
                "type": "brief",
                "title": r["case_title"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in recent_briefs
        ],
    }


@router.get("/lawyer")
async def lawyer_dashboard(user: Annotated[SessionUser, Depends(get_current_user)]):
    uid = user.id

    profile = await profiles_repo.get_or_create_lawyer_profile(uid)
    recent_activity = await activity_repo.get_recent_activity(uid, 10)

    # Stats — mirror the Next.js server action in lib/actions/lawyer-dashboard.ts
    brief_row = await fetch_one("SELECT COUNT(*) as count FROM briefs WHERE user_id = $1", uid)
    research_row = await fetch_one(
        "SELECT COUNT(*) as count FROM research_conversations WHERE user_id = $1", uid
    )
    note_row = await fetch_one("SELECT COUNT(*) as count FROM notes WHERE user_id = $1", uid)

    doc_count = 0
    try:
        d_row = await fetch_one("SELECT COUNT(*) as count FROM documents WHERE user_id = $1", uid)
        doc_count = int(d_row["count"]) if d_row else 0
    except Exception:
        pass

    return {
        "profile": profile,
        "stats": {
            "total_briefs": int(brief_row["count"]) if brief_row else 0,
            "total_research": int(research_row["count"]) if research_row else 0,
            "total_notes": int(note_row["count"]) if note_row else 0,
            "total_documents": doc_count,
        },
        "recent_activity": recent_activity,
    }
