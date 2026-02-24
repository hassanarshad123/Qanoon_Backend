from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.auth import SessionUser, get_current_user
from app.repositories import activity as activity_repo

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/recent")
async def get_recent_activity(
    user: Annotated[SessionUser, Depends(get_current_user)],
    limit: int = Query(default=20, le=100),
):
    return await activity_repo.get_recent_activity(user.id, limit)
