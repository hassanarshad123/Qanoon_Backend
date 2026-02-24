from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import SessionUser, get_current_user, get_optional_user
from app.models.onboarding import OnboardingSubmitRequest, ComingSoonRequest
from app.repositories import onboarding as onboarding_repo

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/submit")
async def submit_onboarding(
    body: OnboardingSubmitRequest,
    user: Annotated[SessionUser | None, Depends(get_optional_user)] = None,
):
    user_id = body.user_id or (user.id if user else None)
    result = await onboarding_repo.submit_onboarding(
        role=body.role,
        email=body.email,
        data=body.data,
        user_id=user_id,
    )
    return result


@router.post("/coming-soon")
async def coming_soon(body: ComingSoonRequest):
    result = await onboarding_repo.submit_coming_soon(body.role, body.email)
    return result
