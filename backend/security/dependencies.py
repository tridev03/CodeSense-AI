"""
SEC-01 & SEC-02: FastAPI Authentication Dependencies.

Provides:
  - get_current_user(token)   → CurrentUser  (requires valid JWT)
  - get_optional_user(token)  → Optional[CurrentUser]  (no-auth for dev mode)

CurrentUser is a lightweight Pydantic model containing:
  - user_id (UUID string from JWT sub claim)
  - email
  - is_superuser

In ENVIRONMENT=development and when AUTH_ENABLED=false, get_current_user
returns a built-in dev user so the API remains usable without credentials.
This dev bypass is DISABLED in production.

Tenant Isolation (SEC-02):
  - require_repo_owner(repository_id, current_user, db)
    Verifies the requesting user owns the repository, raising HTTP 403
    if they do not. Superusers bypass this check.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.security.auth import TokenVerificationError, decode_access_token

# ── Current-user model ────────────────────────────────────────────────────────


class CurrentUser(BaseModel):
    """Authenticated user extracted from a validated JWT."""

    user_id: str       # UUID string matching the 'sub' JWT claim
    email: Optional[str] = None
    is_superuser: bool = False


# ── Dev bypass user (development / testing only) ──────────────────────────────

_DEV_USER = CurrentUser(
    user_id="00000000-0000-0000-0000-000000000001",
    email="dev@localhost",
    is_superuser=True,
)

# ── Bearer token extractor ────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


# ── get_current_user dependency ───────────────────────────────────────────────


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> CurrentUser:
    """
    FastAPI dependency — extract and validate the current user from Bearer JWT.

    Development bypass:
        When ENVIRONMENT=development (or testing) and no token is provided,
        returns _DEV_USER so routes remain testable without credentials.
        This bypass is strictly disabled in production.

    Raises:
        HTTP 401 Unauthorized: when production token is missing or invalid.
    """
    # ── Production: require a valid token ────────────────────────────────────
    if settings.is_production:
        if not credentials or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide a Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _validate_token(credentials.credentials)

    # ── Development / Testing: allow unauthenticated dev bypass ──────────────
    if not credentials or not credentials.credentials:
        return _DEV_USER

    # Token provided even in dev — validate it properly
    return _validate_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[CurrentUser]:
    """
    Like get_current_user but returns None instead of raising 401.
    Use for endpoints that have both authenticated and anonymous behaviors.
    """
    if not credentials or not credentials.credentials:
        if settings.is_production:
            return None
        return _DEV_USER
    try:
        return _validate_token(credentials.credentials)
    except HTTPException:
        return None


def _validate_token(token: str) -> CurrentUser:
    try:
        token_data = decode_access_token(token)
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return CurrentUser(
        user_id=token_data.sub,
        email=token_data.email,
        is_superuser=token_data.is_superuser,
    )


# ── SEC-02: Tenant ownership guard ────────────────────────────────────────────


async def require_repo_owner(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession,
) -> None:
    """
    Ensure current_user owns repository_id.

    Superusers bypass the check (they can access any repository).
    Raises HTTP 403 if the user does not own the repository.
    """
    if current_user.is_superuser:
        return

    from backend.database import crud  # avoid circular imports at module level

    try:
        user_uuid = uuid.UUID(current_user.user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user identity in token.",
        )

    owns = await crud.is_repository_owner(db, repository_id, user_uuid)
    if not owns:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this repository.",
        )
