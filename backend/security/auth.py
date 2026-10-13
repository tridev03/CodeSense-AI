"""
SEC-01: JWT Authentication core utilities.

Provides:
- Password hashing and verification using bcrypt via passlib
- JWT access token creation and decoding (python-jose + HS256)
- TokenData — validated claims model extracted from a token
- Graceful handling of missing/expired/malformed tokens

Token lifecycle:
  Login → create_access_token(data) → Bearer token → decode_access_token(token) → TokenData
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel
import bcrypt

from backend.config.settings import settings

# ── Password hashing ──────────────────────────────────────────────────────────


def get_password_hash(plain: str) -> str:
    """Return bcrypt hash of a plaintext password."""
    # Ensure password is at most 72 bytes to satisfy bcrypt spec
    pwd_bytes = plain.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True iff the plaintext password matches the stored hash."""
    try:
        pwd_bytes = plain.encode("utf-8")[:72]
        hash_bytes = hashed.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


# ── JWT token model ───────────────────────────────────────────────────────────


class TokenData(BaseModel):
    """Validated claims extracted from a JWT access token."""

    sub: str                          # User ID (UUID string)
    email: Optional[str] = None
    is_superuser: bool = False
    exp: Optional[datetime] = None


class TokenResponse(BaseModel):
    """Response body returned by /auth/token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── JWT creation ──────────────────────────────────────────────────────────────

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours default


def create_access_token(
    *,
    subject: str,
    email: Optional[str] = None,
    is_superuser: bool = False,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Mint a signed JWT access token.

    Args:
        subject:     The user's UUID string.
        email:       Optional email for display / logging (not used for authz).
        is_superuser: Whether to embed superuser claim.
        expires_delta: Override the default expiry window.

    Returns:
        Signed JWT string.
    """
    expire_minutes = int(expires_delta.total_seconds() / 60) if expires_delta else _ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if email:
        payload["email"] = email
    if is_superuser:
        payload["is_superuser"] = True

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


# ── JWT verification ──────────────────────────────────────────────────────────


class TokenVerificationError(Exception):
    """Raised when a token is missing, expired, or has invalid claims."""


def decode_access_token(token: str) -> TokenData:
    """
    Decode and validate a JWT access token.

    Raises:
        TokenVerificationError: if the token is invalid, expired, or malformed.

    Returns:
        TokenData with validated claims.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise TokenVerificationError(f"Token validation failed: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise TokenVerificationError("Token missing 'sub' claim.")

    return TokenData(
        sub=sub,
        email=payload.get("email"),
        is_superuser=bool(payload.get("is_superuser", False)),
    )
