"""
Unit tests for the repository file scanner.

Tests:
- Directory ignore rules (.git, node_modules, __pycache__, .venv, dist, etc.)
- Binary and media file exclusion
- File size limit filtering
- Content classification (code, documentation, configuration)
- Language detection
- Relative path calculation and sorting
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest

from backend.ingestion.models import ContentType
from backend.ingestion.scanner import (
    BINARY_EXTENSIONS,
    IGNORED_DIRECTORIES,
    _classify_file,
    _is_ignored_directory,
    _is_ignored_file,
    scan_repository,
)


def test_ignored_directories() -> None:
    """Verify standard ignored directories are correctly detected."""
    assert _is_ignored_directory(".git")
    assert _is_ignored_directory("node_modules")
    assert _is_ignored_directory("__pycache__")
    assert _is_ignored_directory(".venv")
    assert _is_ignored_directory("dist")
    assert _is_ignored_directory("build")
    assert _is_ignored_directory(".next")
    assert _is_ignored_directory("my_package.egg-info")
    assert not _is_ignored_directory("src")
    assert not _is_ignored_directory("backend")
    assert not _is_ignored_directory("components")


def test_ignored_files() -> None:
    """Verify binary, minified, and lock files are ignored."""
    assert _is_ignored_file("test.png", ".png")
    assert _is_ignored_file("bundle.min.js", ".js")
    assert _is_ignored_file("index.js.map", ".map")
    assert _is_ignored_file("package-lock.json", ".json")
    assert _is_ignored_file("poetry.lock", ".lock")
    assert not _is_ignored_file("main.py", ".py")
    assert not _is_ignored_file("app.tsx", ".tsx")
    assert not _is_ignored_file("README.md", ".md")


def test_file_classification() -> None:
    """Verify content type and language detection."""
    # Code files
    ctype, lang = _classify_file("service.py", ".py")
    assert ctype == ContentType.CODE
    assert lang == "python"

    ctype, lang = _classify_file("index.ts", ".ts")
    assert ctype == ContentType.CODE
    assert lang == "typescript"

    ctype, lang = _classify_file("App.jsx", ".jsx")
    assert ctype == ContentType.CODE
    assert lang == "javascript"

    # Documentation files
    ctype, lang = _classify_file("README.md", ".md")
    assert ctype == ContentType.DOCUMENTATION
    assert lang is None

    ctype, lang = _classify_file("CONTRIBUTING.txt", ".txt")
    assert ctype == ContentType.DOCUMENTATION

    # Configuration files
    ctype, lang = _classify_file("tsconfig.json", ".json")
    assert ctype == ContentType.CONFIGURATION

    ctype, lang = _classify_file("docker-compose.yml", ".yml")
    assert ctype == ContentType.CONFIGURATION


def test_scan_repository(tmp_path: Path) -> None:
    """Test full repository scan on a temporary directory with various files."""
    # Create sample repo structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass", encoding="utf-8")
    (tmp_path / "src" / "utils.ts").write_text("export function add() {}", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project Docs", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")

    # Create ignored files and directories
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module code", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00\x01\x02")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # Run scan
    discovered = scan_repository(str(tmp_path))

    paths = [f.path for f in discovered]
    assert "src/main.py" in paths
    assert "src/utils.ts" in paths
    assert "README.md" in paths
    assert "package.json" in paths

    # Ignored paths must NOT be present
    assert not any(".git" in p for p in paths)
    assert not any("node_modules" in p for p in paths)
    assert not any("__pycache__" in p for p in paths)
    assert not any("logo.png" in p for p in paths)


def test_scan_repository_max_file_size(tmp_path: Path) -> None:
    """Test that oversized files are filtered out during scan."""
    small_file = tmp_path / "small.py"
    small_file.write_text("print('small')", encoding="utf-8")

    large_file = tmp_path / "large.py"
    # Write 2MB file
    large_file.write_text("x = 1\n" * 200_000, encoding="utf-8")

    # Scan with 1MB limit
    discovered = scan_repository(str(tmp_path), max_file_size_mb=1.0)
    paths = [f.path for f in discovered]

    assert "small.py" in paths
    assert "large.py" not in paths

