"""
Pydantic schemas for authentication and user management (SEC-01).

Schemas:
  - UserCreate       — POST /auth/register
  - UserResponse     — GET /auth/me
  - LoginRequest     — POST /auth/token (form or JSON)
  - TokenResponse    — Token response body
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 characters)",
    )

    @field_validator("password")
    @classmethod
    def password_not_trivial(cls, v: str) -> str:
        if v.lower() in ("password", "12345678", "qwerty123"):
            raise ValueError("Password is too common. Choose a stronger password.")
        return v


class UserResponse(BaseModel):
    """Public user profile returned by the API — never includes password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime


class LoginRequest(BaseModel):
    """Request body for POST /auth/token (JSON variant)."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Response body returned by /auth/token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")


class ResetPasswordRequest(BaseModel):
    """Request body for POST /auth/reset-password."""

    email: EmailStr
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (min 8 characters)",
    )

    @field_validator("new_password")
    @classmethod
    def password_not_trivial(cls, v: str) -> str:
        if v.lower() in ("password", "12345678", "qwerty123"):
            raise ValueError("Password is too common. Choose a stronger password.")
        return v

