"""
backend.security package — Workstream 1: Authentication, Authorization & Input Validation.

Exports:
  - TokenData          — JWT claims model
  - UserInDB           — user record from DB (hashed password)
  - create_access_token
  - verify_password / get_password_hash
  - decode_access_token
  - get_current_user    — FastAPI dependency
  - require_repo_owner  — FastAPI dependency (tenant isolation)
  - GitUrlValidator     — SEC-04: strict URL parsing & SSRF checks
  - FilesystemSandbox   — SEC-06: path traversal prevention
"""
from backend.security.auth import (
    TokenData,
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from backend.security.dependencies import get_current_user, get_optional_user
from backend.security.validators import FilesystemSandbox, GitUrlValidator

__all__ = [
    "TokenData",
    "create_access_token",
    "decode_access_token",
    "get_password_hash",
    "verify_password",
    "get_current_user",
    "get_optional_user",
    "GitUrlValidator",
    "FilesystemSandbox",
]
