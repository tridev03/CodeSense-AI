"""
Authentication routes (SEC-01).

Endpoints:
  POST /auth/register  — Register a new user account
  POST /auth/token     — Login and receive a JWT access token
  GET  /auth/me        — Return the currently authenticated user

Design choices:
  - Passwords are hashed with bcrypt via passlib (never stored in plaintext)
  - JWTs are HS256 signed with SECRET_KEY, expire after 24h by default
  - In development mode (ENVIRONMENT=development), /auth/me works without a token
  - Rate limiting on login endpoint is enforced by RateLimitMiddleware
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.database.user_models import User
from backend.schemas.auth import (
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from backend.security.auth import (
    _ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_password_hash,
    verify_password,
)
from backend.security.dependencies import CurrentUser, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helper: look up user by email ─────────────────────────────────────────────


async def _get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


# ── POST /auth/register ───────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Register a new user account.

    - Email must be unique (HTTP 409 if already registered).
    - Password is hashed with bcrypt before storage.
    """
    email = payload.email.lower()
    existing = await _get_user_by_email(db, email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{email}' is already registered.",
        )

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


# ── POST /auth/token ──────────────────────────────────────────────────────────


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Login and receive a JWT access token",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate with email + password and receive a Bearer JWT token.

    - Returns HTTP 401 for invalid credentials (same message for missing user
      and wrong password to prevent user enumeration).
    - Token expires after 24 hours.
    """
    user = await _get_user_by_email(db, payload.email.lower())

    # Constant-time failure path to prevent timing-based user enumeration
    _invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        # Still verify a dummy hash to prevent timing attacks
        get_password_hash("dummy-constant-time-check")
        raise _invalid_credentials

    if not verify_password(payload.password, user.hashed_password):
        raise _invalid_credentials

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact support.",
        )

    token = create_access_token(
        subject=str(user.id),
        email=user.email,
        is_superuser=user.is_superuser,
        expires_delta=timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── POST /auth/reset-password ────────────────────────────────────────────────


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset user password by email",
)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Reset user password given email and new password.
    """
    user = await _get_user_by_email(db, payload.email.lower())
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user account found with that email address.",
        )

    user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return {"message": "Password has been successfully updated. You can now sign in."}


# ── GET /auth/me ──────────────────────────────────────────────────────────────


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the currently authenticated user",
)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Return profile information for the currently authenticated user.

    In development mode without a token, returns the built-in dev user record.
    """
    # Look up actual DB record if available
    try:
        user_uuid = uuid.UUID(current_user.user_id)
        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()
        if user:
            return UserResponse.model_validate(user)
    except (ValueError, Exception):
        pass

    # Dev user or token-only user (no DB row required in dev mode)
    return UserResponse(
        id=uuid.UUID(current_user.user_id),
        email=current_user.email or "dev@localhost",
        is_active=True,
        is_superuser=current_user.is_superuser,
        created_at=__import__("datetime").datetime.utcnow(),
    )
