"""
Telemetry sanitization and secret redaction (OBS-05).

Provides high-performance pattern-based and key-based redaction to ensure:
- API keys, passwords, bearer tokens, JWTs, connection strings are NEVER exported to telemetry.
- Private source code and raw prompts are sanitized or omitted by default.
- Safe metrics, document IDs, scores, and execution latencies remain intact.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Union

# Common sensitive parameter names (case-insensitive)
SENSITIVE_KEY_PATTERNS: Set[str] = {
    "password",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "api_key",
    "apikey",
    "groq_api_key",
    "qdrant_api_key",
    "github_token",
    "langfuse_public_key",
    "langfuse_secret_key",
    "private_key",
    "client_secret",
    "credentials",
    "database_url",
    "redis_url",
}

# Regex patterns matching secret structures in text strings
SECRET_REGEXES: List[re.Pattern] = [
    # Bearer tokens
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    # JWT tokens (three base64url segments separated by dots)
    re.compile(r"ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}\.[A-Za-z0-9._-]{10,}"),
    # Generic API key patterns (e.g. gsk_..., ghp_..., etc.)
    re.compile(r"(gsk|ghp|gho|pat|sk|pk)_[a-zA-Z0-9]{20,}"),
    # DB / Redis connection strings with credentials: scheme://user:pass@host
    re.compile(r"://([^:]+):([^@]+)@"),
    # Password key-value pairs
    re.compile(r"(password|secret|key)\s*[:=]\s*['\"]?([^'\"\s,]+)['\"]?", re.IGNORECASE),
]

REDACTED_PLACEHOLDER = "[REDACTED]"


def redact_string(text: str) -> str:
    """Sanitize secrets out of arbitrary string content."""
    if not text or not isinstance(text, str):
        return text

    redacted = text
    # 1. Mask connection string passwords: scheme://user:pass@host -> scheme://user:[REDACTED]@host
    redacted = re.sub(r"://([^:]+):([^@]+)@", r"://\1:[REDACTED]@", redacted)

    # 2. Mask other known secret signatures
    for pattern in SECRET_REGEXES:
        if pattern != SECRET_REGEXES[3]:  # skip connection string (already handled above)
            redacted = pattern.sub(REDACTED_PLACEHOLDER, redacted)

    return redacted


def redact_telemetry_data(data: Any, max_string_len: int = 1000) -> Any:
    """
    Recursively sanitize dictionaries, lists, and primitives before sending to telemetry.

    - Truncates oversized string content (e.g., massive source code snippets).
    - Replaces values whose keys match sensitive key patterns.
    - Runs regex secret scrubbers on all string values.
    """
    if isinstance(data, dict):
        sanitized_dict: Dict[str, Any] = {}
        for key, value in data.items():
            k_lower = str(key).lower().strip()
            if any(k_lower == s or k_lower.endswith(f"_{s}") for s in SENSITIVE_KEY_PATTERNS):
                sanitized_dict[key] = REDACTED_PLACEHOLDER
            else:
                sanitized_dict[key] = redact_telemetry_data(value, max_string_len)
        return sanitized_dict

    elif isinstance(data, (list, tuple, set)):
        sanitized_list = [redact_telemetry_data(item, max_string_len) for item in data]
        return type(data)(sanitized_list) if not isinstance(data, set) else set(sanitized_list)

    elif isinstance(data, str):
        cleaned = redact_string(data)
        if len(cleaned) > max_string_len:
            return cleaned[:max_string_len] + f"... [truncated {len(cleaned) - max_string_len} chars]"
        return cleaned

    return data
