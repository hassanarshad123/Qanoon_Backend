import logging

import bcrypt
from fastapi import APIRouter

from app.models.auth import (
    ActionResult,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SignupRequest,
)
from app.repositories import users as users_repo
from app.repositories import password_reset as pr_repo
from app.services.email_service import send_password_reset_email

logger = logging.getLogger("qanoonai")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=ActionResult)
async def signup(body: SignupRequest):
    existing = await users_repo.get_user_by_email(body.email)
    if existing:
        return ActionResult(success=False, error="An account with this email already exists")

    try:
        await users_repo.create_user(body.email, body.password, body.name, body.role)
        return ActionResult(success=True)
    except Exception:
        return ActionResult(success=False, error="Failed to create account. Please try again.")


@router.post("/forgot-password", response_model=ActionResult)
async def forgot_password(body: ForgotPasswordRequest):
    user = await users_repo.get_user_by_email(body.email)
    # Always return success to prevent email enumeration
    if not user:
        return ActionResult(success=True)

    try:
        token = await pr_repo.create_token(user["id"])
        await send_password_reset_email(user["email"], token)
    except Exception:
        # Log for debugging but don't reveal email existence to the client
        logger.exception("Failed to send password reset email for user %s", user["id"])

    return ActionResult(success=True)


@router.post("/reset-password", response_model=ActionResult)
async def reset_password(body: ResetPasswordRequest):
    token_data = await pr_repo.validate_token(body.token)
    if not token_data:
        return ActionResult(
            success=False,
            error="Invalid or expired reset link. Please request a new one.",
        )

    try:
        password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(12)).decode()
        await users_repo.update_user_password(token_data["user_id"], password_hash)
        await pr_repo.consume_token(body.token)
        return ActionResult(success=True)
    except Exception:
        return ActionResult(success=False, error="Failed to reset password. Please try again.")
