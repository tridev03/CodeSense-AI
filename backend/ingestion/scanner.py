"""
File scanner: discovers, classifies, and filters repository files.

Responsibilities:
- Walk the repository directory tree
- Skip ignored directories and files (binary, too large, generated)
- Classify files as code / documentation / configuration
- Detect file encoding safely
- Return a list of DiscoveredFile objects for the parser stage

Design decision: All ignore rules are centralized here (not scattered across
parsers or chunkers). This makes the filtering logic testable in isolation.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set

from backend.ingestion.models import ContentType, DiscoveredFile

logger = logging.getLogger(__name__)

# ─── Ignore Rules ─────────────────────────────────────────────────────────────
# Directories and files that should NEVER be indexed.

IGNORED_DIRECTORIES: FrozenSet[str] = frozenset({
    # Version control
    ".git", ".svn", ".hg",
    # Dependencies
    "node_modules", "bower_components", "vendor",
    # Python
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", ".eggs", "*.egg-info",
    # Virtual environments
    ".venv", "venv", "env", ".env",
    # Build artifacts
    "build", "dist", "_build", "out", "target",
    # Frontend build
    ".next", ".nuxt", ".svelte-kit", ".output",
    # IDE
    ".idea", ".vscode", ".vs",
    # Misc
    ".cache", ".tmp", "tmp", "temp",
    "coverage", "htmlcov", ".nyc_output",
    # Terraform / IaC
    ".terraform",
})

IGNORED_FILE_PATTERNS: FrozenSet[str] = frozenset({
    # Lock files
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "composer.lock",
    "Gemfile.lock", "Cargo.lock",
    # Generated / minified
    ".min.js", ".min.css", ".bundle.js",
    ".map",       # source maps
    # Binary / media (checked by extension below)
    # Environment secrets (should not be indexed)
    ".env",
})

BINARY_EXTENSIONS: FrozenSet[str] = frozenset({
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".tiff", ".tif",
    # Audio / Video
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg",
    # Fonts
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # Compiled / Binary
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib",
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",
    ".wasm",
    # Data / Database
    ".db", ".sqlite", ".sqlite3", ".mdb",
    ".pickle", ".pkl",
    # Documents (not useful for code RAG)
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # ML model files
    ".bin", ".safetensors", ".gguf", ".onnx", ".h5", ".pb",
    ".pt", ".pth",
})

# ─── Language & Content Type Maps ─────────────────────────────────────────────

LANGUAGE_MAP: Dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".r": "r",
    ".R": "r",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".lua": "lua",
    ".sql": "sql",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".vue": "vue",
    ".svelte": "svelte",
}

DOCUMENTATION_EXTENSIONS: FrozenSet[str] = frozenset({
    ".md", ".markdown", ".rst", ".txt", ".adoc", ".asciidoc",
})

DOCUMENTATION_FILENAMES: FrozenSet[str] = frozenset({
    "readme", "changelog", "changes", "history",
    "contributing", "authors", "license", "licence",
    "code_of_conduct", "security", "todo",
})

CONFIGURATION_EXTENSIONS: FrozenSet[str] = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".properties",
})

CONFIGURATION_FILENAMES: FrozenSet[str] = frozenset({
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "makefile", "cmakelists.txt",
    ".gitignore", ".dockerignore", ".editorconfig",
    ".eslintrc", ".prettierrc", ".babelrc",
    "tsconfig.json", "jsconfig.json",
    "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "constraints.txt",
    "package.json", "cargo.toml", "go.mod", "go.sum",
    "gemfile", "build.gradle", "pom.xml",
    ".env.example", ".env.sample", ".env.template",
})


# ─── Scanner Implementation ──────────────────────────────────────────────────


def _is_ignored_directory(dir_name: str) -> bool:
    """Check if a directory should be skipped entirely."""
    name_lower = dir_name.lower()
    if name_lower in IGNORED_DIRECTORIES:
        return True
    # Egg-info directories
    if name_lower.endswith(".egg-info"):
        return True
    return False


def _is_ignored_file(filename: str, extension: str) -> bool:
    """Check if a file should be skipped."""
    if extension in BINARY_EXTENSIONS:
        return True
    if filename in IGNORED_FILE_PATTERNS:
        return True
    # Minified files
    if filename.endswith(".min.js") or filename.endswith(".min.css"):
        return True
    # Source maps
    if filename.endswith(".map"):
        return True
    return False


def _classify_file(
    filename: str, extension: str
) -> tuple[ContentType, Optional[str]]:
    """
    Determine content type and programming language for a file.

    Returns:
        (content_type, language_or_none)
    """
    name_lower = filename.lower()
    stem_lower = Path(filename).stem.lower()

    # Documentation by filename (e.g. README, CHANGELOG)
    if stem_lower in DOCUMENTATION_FILENAMES:
        return ContentType.DOCUMENTATION, None

    # Documentation by extension
    if extension in DOCUMENTATION_EXTENSIONS:
        return ContentType.DOCUMENTATION, None

    # Configuration by filename
    if name_lower in CONFIGURATION_FILENAMES:
        return ContentType.CONFIGURATION, None

    # Configuration by extension (but not if it is also a language)
    if extension in CONFIGURATION_EXTENSIONS and extension not in LANGUAGE_MAP:
        return ContentType.CONFIGURATION, None

    # Code by extension
    if extension in LANGUAGE_MAP:
        return ContentType.CODE, LANGUAGE_MAP[extension]

    # Config files that share extensions with languages (.json, .xml) — treat as config
    if extension in CONFIGURATION_EXTENSIONS:
        return ContentType.CONFIGURATION, None

    return ContentType.UNKNOWN, None


def _detect_encoding(file_path: str) -> str:
    """
    Attempt to detect file encoding by reading first bytes.

    Falls back to utf-8 on any error. We intentionally don't add chardet
    as a hard dependency — simple heuristics cover the vast majority of
    source code files.
    """
    try:
        with open(file_path, "rb") as f:
            raw = f.read(8192)

        # BOM detection
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if raw.startswith(b"\xff\xfe"):
            return "utf-16-le"
        if raw.startswith(b"\xfe\xff"):
            return "utf-16-be"

        # Try utf-8 decode
        raw.decode("utf-8")
        return "utf-8"
    except (UnicodeDecodeError, OSError):
        # Try latin-1 as a fallback (always succeeds but may be wrong)
        return "latin-1"


def scan_repository(
    repo_root: str,
    *,
    max_file_size_mb: float = 5.0,
    extra_ignore_dirs: Optional[Set[str]] = None,
) -> List[DiscoveredFile]:
    """
    Walk the repository tree and return classified, filtered files.

    Args:
        repo_root: Absolute path to the repository root directory.
        max_file_size_mb: Maximum file size in MB. Files larger are skipped.
        extra_ignore_dirs: Additional directory names to skip.

    Returns:
        List of DiscoveredFile objects, sorted by path.
    """
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository root does not exist: {root}")

    max_size_bytes = int(max_file_size_mb * 1024 * 1024)
    ignore_dirs = IGNORED_DIRECTORIES | (extra_ignore_dirs or set())
    discovered: List[DiscoveredFile] = []
    skipped_count = 0

    for dirpath, dirnames, filenames in os.walk(str(root)):
        # Prune ignored directories IN-PLACE so os.walk doesn't descend
        dirnames[:] = [
            d for d in dirnames
            if not _is_ignored_directory(d) and d not in ignore_dirs
        ]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            extension = Path(filename).suffix.lower()

            # Skip ignored files
            if _is_ignored_file(filename, extension):
                skipped_count += 1
                continue

            # Skip files that are too large
            try:
                size = os.path.getsize(filepath)
            except OSError:
                skipped_count += 1
                continue

            if size > max_size_bytes:
                logger.debug(
                    "Skipping oversized file: %s (%d bytes)", filepath, size
                )
                skipped_count += 1
                continue

            if size == 0:
                skipped_count += 1
                continue

            # Classify
            content_type, language = _classify_file(filename, extension)
            if content_type == ContentType.UNKNOWN:
                skipped_count += 1
                continue

            # Detect encoding
            encoding = _detect_encoding(filepath)

            # Compute relative path
            rel_path = os.path.relpath(filepath, str(root)).replace("\\", "/")

            discovered.append(
                DiscoveredFile(
                    path=rel_path,
                    absolute_path=filepath,
                    content_type=content_type,
                    language=language,
                    size_bytes=size,
                    encoding=encoding,
                )
            )

    discovered.sort(key=lambda f: f.path)

    logger.info(
        "Scanner finished: discovered=%d, skipped=%d, root=%s",
        len(discovered),
        skipped_count,
        str(root),
    )
    return discovered

