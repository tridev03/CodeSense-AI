"""
SEC-04, SEC-05, SEC-06: Input Validation & Sandbox Utilities.

GitUrlValidator — SEC-04 & SEC-05:
  - Strict RFC 3986 URL parsing
  - HTTPS-only scheme enforcement
  - Allowlisted hostname check (github.com only by default)
  - Rejects embedded credentials, unusual ports, non-HTTP schemes
  - SSRF protection: blocks loopback, RFC-1918 private ranges,
    link-local, multicast, cloud metadata endpoint

FilesystemSandbox — SEC-06:
  - Ensures all local paths remain within approved base directory
  - Resolves symlinks and normalizes before comparison
  - Rejects path traversal (../../), absolute escapes, null bytes
  - Used during local repository indexing to prevent reading
    arbitrary files outside the storage root
"""
from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


# ── SSRF / Egress Protection ──────────────────────────────────────────────────

#: Cloud metadata endpoints that must always be blocked regardless of IP.
_BLOCKED_HOSTNAME_PATTERNS: list[re.Pattern] = [
    re.compile(r"^169\.254\.169\.254$"),        # AWS/GCP/Azure metadata
    re.compile(r"^metadata\.google\.internal$"),
    re.compile(r"^metadata\.internal$"),
]

#: Reserved/private address ranges to block (SEC-05).
_BLOCKED_IP_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC-1918 private
    ipaddress.ip_network("172.16.0.0/12"),    # RFC-1918 private
    ipaddress.ip_network("192.168.0.0/16"),   # RFC-1918 private
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / APIPA
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),        # "This" network
]


def _is_ip_blocked(hostname: str) -> bool:
    """Return True if the hostname resolves to a blocked (private/internal) IP."""
    # First check blocked hostname patterns (fast, no DNS)
    for pattern in _BLOCKED_HOSTNAME_PATTERNS:
        if pattern.match(hostname):
            return True

    # DNS resolution check
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, OSError):
        # If DNS fails, we can't confirm it's safe; reject it.
        return True

    for info in infos:
        addr_str = info[4][0]
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        for network in _BLOCKED_IP_NETWORKS:
            if addr in network:
                return True
    return False


# ── SEC-04: Git URL Validator ─────────────────────────────────────────────────


class GitUrlValidationError(ValueError):
    """Raised when a repository URL fails security validation."""


_ALLOWED_GITHUB_HOSTNAME = "github.com"


class GitUrlValidator:
    """
    Validates and normalizes repository URLs per SEC-04 and SEC-05.

    Rules:
    - Only HTTPS scheme is allowed (no git://, ssh://, http://, file://).
    - Only github.com hostname is allowed by default.
    - Embedded credentials (user:pass@host) are rejected.
    - Non-standard ports are rejected.
    - URL must include at least owner/repo path segments.
    - SSRF: hostname must not resolve to private/loopback/metadata IPs.

    For local paths, use FilesystemSandbox instead.
    """

    def __init__(
        self,
        allowed_hostnames: Optional[list[str]] = None,
        check_ssrf: bool = True,
    ) -> None:
        self._allowed = set(allowed_hostnames or [_ALLOWED_GITHUB_HOSTNAME])
        self._check_ssrf = check_ssrf

    def validate(self, url: str) -> str:
        """
        Validate and return the normalized URL.

        Raises:
            GitUrlValidationError: with a safe, user-readable message.
        """
        url = url.strip()

        if not url:
            raise GitUrlValidationError("Repository URL cannot be empty.")

        # Null byte / control characters
        if any(c in url for c in ("\x00", "\n", "\r")):
            raise GitUrlValidationError("Repository URL contains invalid characters.")

        parsed = urlparse(url)

        # 1. Scheme must be https
        if parsed.scheme.lower() != "https":
            raise GitUrlValidationError(
                f"Only HTTPS repository URLs are supported. Got scheme: '{parsed.scheme or '(none)'}'. "
                "Use https://github.com/owner/repo"
            )

        # 2. No embedded credentials
        if parsed.username or parsed.password:
            raise GitUrlValidationError(
                "Repository URLs must not contain embedded credentials."
            )

        # 3. Hostname must be in allowlist
        hostname = (parsed.hostname or "").lower().strip(".")
        if hostname not in self._allowed:
            raise GitUrlValidationError(
                f"Repository host '{hostname}' is not in the allowed list. "
                f"Allowed: {sorted(self._allowed)}"
            )

        # 4. No non-standard ports
        if parsed.port is not None:
            raise GitUrlValidationError(
                f"Non-standard port {parsed.port} is not allowed in repository URLs."
            )

        # 5. Must have owner/repo path
        path = parsed.path.rstrip("/").removesuffix(".git")
        segments = [s for s in path.split("/") if s]
        if len(segments) < 2:
            raise GitUrlValidationError(
                "GitHub URL must include owner and repository: https://github.com/<owner>/<repo>"
            )

        # 6. SSRF check: resolve hostname
        if self._check_ssrf and _is_ip_blocked(hostname):
            raise GitUrlValidationError(
                f"Repository hostname '{hostname}' resolved to a blocked or private address."
            )

        # Normalize: strip trailing slash, remove .git suffix
        normalized = f"https://{hostname}/{'/'.join(segments)}"
        return normalized


# ── SEC-06: Filesystem Path Sandbox ──────────────────────────────────────────


class FilesystemSandboxError(PermissionError):
    """Raised when a requested path escapes the sandbox root."""


class FilesystemSandbox:
    """
    Ensures file access remains within an approved base directory.

    Usage:
        sandbox = FilesystemSandbox(base="/app/storage/repos")
        safe_path = sandbox.resolve("some-repo/src/main.py")
        # Raises FilesystemSandboxError if path escapes /app/storage/repos
    """

    def __init__(self, base: str | Path) -> None:
        self._base = Path(base).resolve()

    @property
    def base(self) -> Path:
        return self._base

    def resolve(self, requested: str | Path) -> Path:
        """
        Resolve a path relative to the sandbox base.

        Raises:
            FilesystemSandboxError: if the resolved path is outside the base.
            ValueError: if the input contains null bytes or control characters.
        """
        raw = str(requested)

        # Null bytes and control characters
        if "\x00" in raw or any(ord(c) < 0x20 for c in raw):
            raise ValueError("Path contains null bytes or control characters.")

        try:
            candidate = (self._base / raw).resolve()
        except (OSError, ValueError) as exc:
            raise FilesystemSandboxError(
                f"Cannot resolve requested path: {exc}"
            ) from exc

        # Strict prefix check after resolving symlinks
        try:
            candidate.relative_to(self._base)
        except ValueError:
            raise FilesystemSandboxError(
                f"Access denied: path '{raw}' resolves outside the sandbox root."
            )

        return candidate

    def is_safe(self, requested: str | Path) -> bool:
        """Return True if the path is within the sandbox (no exception)."""
        try:
            self.resolve(requested)
            return True
        except (FilesystemSandboxError, ValueError):
            return False
