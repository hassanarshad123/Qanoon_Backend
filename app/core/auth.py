"""
NextAuth v5 JWE token verification for FastAPI.

NextAuth (Auth.js) v5 beta encrypts session tokens as JWE (JSON Web Encryption)
using A256CBC-HS512. The encryption key is derived from AUTH_SECRET via HKDF.

Flow:
1. Extract `next-auth.session-token` (or `__Secure-next-auth.session-token`) cookie
2. Derive encryption key from AUTH_SECRET using HKDF(SHA-256, info="Auth.js Generated Encryption Key")
3. Decrypt JWE using A256CBC-HS512
4. Parse the JWT claims to get user info
"""

import hashlib
import json
import logging
from typing import Annotated

logger = logging.getLogger("qanoonai")

from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives import hashes
from fastapi import Cookie, Depends, HTTPException, Request, status
from jose import jwe
from pydantic import BaseModel

from app.config import settings


class SessionUser(BaseModel):
    id: str
    email: str
    name: str | None = None
    role: str
    onboarding_completed: bool = False


# Cookie names NextAuth uses
_COOKIE_NAME = "authjs.session-token"
_SECURE_COOKIE_NAME = "__Secure-authjs.session-token"


def _derive_encryption_key(secret: str) -> bytes:
    """
    Derive the 64-byte encryption key that Auth.js uses for JWE.
    Auth.js uses HKDF with SHA-256, no salt, info="Auth.js Generated Encryption Key",
    deriving a 64-byte key (for A256CBC-HS512 = AES-256-CBC + HMAC-SHA-512).

    The input key material is the raw UTF-8 bytes of AUTH_SECRET.
    """
    # Auth.js uses HKDF-Expand (not full HKDF with extract+expand) with SHA-256
    # The input key material is derived by hashing AUTH_SECRET with SHA-512
    # then truncated to 32 bytes for the HKDF PRK
    ikm = secret.encode("utf-8")

    # Auth.js (via jose library) does:
    # 1. HKDF extract with empty salt → PRK = HMAC-SHA256(salt="", ikm=secret)
    # 2. HKDF expand with info="Auth.js Generated Encryption Key" → 64 bytes
    # We replicate this using cryptography library

    # Step 1: Extract — HMAC-SHA256 with empty salt
    import hmac
    prk = hmac.new(
        b"\x00" * 32,  # empty salt padded to hash length
        ikm,
        hashlib.sha256,
    ).digest()

    # Step 2: Expand — HKDF-Expand with the PRK
    hkdf = HKDFExpand(
        algorithm=hashes.SHA256(),
        length=64,  # A256CBC-HS512 needs 64 bytes
        info=b"Auth.js Generated Encryption Key",
    )
    return hkdf.derive(prk)


# Pre-compute the key at import time (settings are loaded by then)
_ENCRYPTION_KEY = _derive_encryption_key(settings.auth_secret)


def _extract_session_token(request: Request) -> str | None:
    """Extract the NextAuth session token from cookies."""
    token = request.cookies.get(_SECURE_COOKIE_NAME)
    if not token:
        token = request.cookies.get(_COOKIE_NAME)
    return token


def _decrypt_token(token: str) -> dict:
    """Decrypt a NextAuth JWE token and return the payload claims."""
    try:
        payload_bytes = jwe.decrypt(token, _ENCRYPTION_KEY)
        if isinstance(payload_bytes, bytes):
            payload = json.loads(payload_bytes.decode("utf-8"))
        else:
            payload = json.loads(payload_bytes)
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid session token: {e}",
        )


async def get_current_user(request: Request) -> SessionUser:
    """
    FastAPI dependency that extracts and verifies the NextAuth session.
    Usage: `user: SessionUser = Depends(get_current_user)`
    """
    token = _extract_session_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    claims = _decrypt_token(token)

    # NextAuth stores custom fields in the JWT token
    return SessionUser(
        id=claims.get("id", claims.get("sub", "")),
        email=claims.get("email", ""),
        name=claims.get("name"),
        role=claims.get("role", ""),
        onboarding_completed=claims.get("onboardingCompleted", False),
    )


async def get_optional_user(request: Request) -> SessionUser | None:
    """Like get_current_user but returns None instead of raising."""
    token = _extract_session_token(request)
    if not token:
        return None
    try:
        claims = _decrypt_token(token)
        return SessionUser(
            id=claims.get("id", claims.get("sub", "")),
            email=claims.get("email", ""),
            name=claims.get("name"),
            role=claims.get("role", ""),
            onboarding_completed=claims.get("onboardingCompleted", False),
        )
    except HTTPException:
        return None


async def require_admin(user: Annotated[SessionUser, Depends(get_current_user)]) -> SessionUser:
    """Dependency that requires the user to be an admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def require_role(*roles: str):
    """Factory for role-checking dependencies.

    Usage: Depends(require_role("judge")) or Depends(require_role("judge", "lawyer"))
    """
    async def _check(user: Annotated[SessionUser, Depends(get_current_user)]) -> SessionUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(roles)}",
            )
        return user
    return _check
