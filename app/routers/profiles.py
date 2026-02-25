from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import SessionUser, require_role
from app.models.profiles import (
    JudgeProfileUpdate,
    LawyerProfileUpdate,
    ChapterCompleteRequest,
    SectionVisitRequest,
)
from app.repositories import profiles as profiles_repo

router = APIRouter(prefix="/profiles", tags=["profiles"])


# ---------------------------------------------------------------------------
# Judge profile
# ---------------------------------------------------------------------------

_require_judge = require_role("judge", "admin")
_require_lawyer = require_role("lawyer", "admin")


@router.get("/judge")
async def get_judge_profile(user: Annotated[SessionUser, Depends(_require_judge)]):
    return await profiles_repo.get_or_create_judge_profile(user.id)


@router.put("/judge")
async def update_judge_profile(
    body: JudgeProfileUpdate,
    user: Annotated[SessionUser, Depends(_require_judge)],
):
    return await profiles_repo.update_judge_profile(user.id, body.model_dump(exclude_none=True))


@router.get("/judge/tour-status")
async def judge_tour_status(user: Annotated[SessionUser, Depends(_require_judge)]):
    completed = await profiles_repo.is_judge_tour_completed(user.id)
    return {"tour_completed": completed}


@router.post("/judge/tour-complete")
async def judge_tour_complete(user: Annotated[SessionUser, Depends(_require_judge)]):
    await profiles_repo.mark_judge_tour_complete(user.id)
    return {"success": True}


# ---------------------------------------------------------------------------
# Lawyer profile
# ---------------------------------------------------------------------------

@router.get("/lawyer")
async def get_lawyer_profile(user: Annotated[SessionUser, Depends(_require_lawyer)]):
    return await profiles_repo.get_or_create_lawyer_profile(user.id)


@router.put("/lawyer")
async def update_lawyer_profile(
    body: LawyerProfileUpdate,
    user: Annotated[SessionUser, Depends(_require_lawyer)],
):
    return await profiles_repo.update_lawyer_profile(user.id, body.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Lawyer tour state
# ---------------------------------------------------------------------------

@router.get("/lawyer/tour-state")
async def get_lawyer_tour_state(user: Annotated[SessionUser, Depends(_require_lawyer)]):
    return await profiles_repo.get_lawyer_tour_state(user.id)


@router.patch("/lawyer/tour-state")
async def patch_lawyer_tour_state(
    body: dict,
    user: Annotated[SessionUser, Depends(_require_lawyer)],
):
    return await profiles_repo.update_lawyer_tour_state(user.id, body)


@router.post("/lawyer/tour-chapter-complete")
async def lawyer_tour_chapter_complete(
    body: ChapterCompleteRequest,
    user: Annotated[SessionUser, Depends(_require_lawyer)],
):
    return await profiles_repo.update_lawyer_tour_state(user.id, {body.chapter_id: True})


@router.post("/lawyer/tour-section-visit")
async def lawyer_tour_section_visit(
    body: SectionVisitRequest,
    user: Annotated[SessionUser, Depends(_require_lawyer)],
):
    from datetime import datetime, timezone
    current = await profiles_repo.get_lawyer_tour_state(user.id)
    visited = current.get("visitedSections", {})
    if body.route in visited:
        return current
    return await profiles_repo.update_lawyer_tour_state(user.id, {
        "visitedSections": {**visited, body.route: datetime.now(timezone.utc).isoformat()},
    })


@router.post("/lawyer/tour-welcome-shown")
async def lawyer_tour_welcome_shown(user: Annotated[SessionUser, Depends(_require_lawyer)]):
    return await profiles_repo.update_lawyer_tour_state(user.id, {"welcomeShown": True})


@router.post("/lawyer/tour-reset")
async def lawyer_tour_reset(user: Annotated[SessionUser, Depends(_require_lawyer)]):
    return await profiles_repo.reset_lawyer_tour(user.id)
