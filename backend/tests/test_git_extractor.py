"""
Unit tests for Git history extractor and chunk generator.

Tests:
- Detection of Git vs non-Git repositories
- Extraction of commit history (hashes, authors, timestamps, diffs)
- Conversion of Git commits to searchable CodeChunks
- Commit registry lifecycle (store, get, delete)
"""
from __future__ import annotations

from pathlib import Path
import pytest

from backend.ingestion.git_extractor import (
    commits_to_chunks,
    create_mock_git_history,
    delete_stored_commits,
    extract_commit_history,
    get_stored_commits,
    is_git_repository,
    store_commits,
)
from backend.ingestion.models import ContentType, GitCommitInfo


@pytest.fixture
def sample_git_repo(tmp_path: Path) -> Path:
    """Create a test repository folder with simulated Git history."""
    commits = [
        GitCommitInfo(
            hash="2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
            short_hash="2b3c4d5e",
            author_name="Alice Engineer",
            author_email="alice@example.com",
            date="2026-04-02T15:30:00Z",
            message="Fix: Allow valid users to authenticate",
            changed_files=["auth.py"],
            diff_summary="--- auth.py\n+++ auth.py\n@@ -1 +1 @@\n-def authenticate(): return False\n+def authenticate(): return True\n",
        ),
        GitCommitInfo(
            hash="1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
            short_hash="1a2b3c4d",
            author_name="Alice Engineer",
            author_email="alice@example.com",
            date="2026-04-01T10:00:00Z",
            message="Initial commit with basic auth",
            changed_files=["auth.py"],
            diff_summary="--- /dev/null\n+++ auth.py\n@@ -0,0 +1 @@\n+def authenticate(): return False\n",
        ),
    ]
    create_mock_git_history(str(tmp_path), commits)
    (tmp_path / "auth.py").write_text("def authenticate(): return True\n", encoding="utf-8")
    return tmp_path


def test_is_git_repository(sample_git_repo: Path, tmp_path: Path) -> None:
    """Verify Git repository detection."""
    assert is_git_repository(str(sample_git_repo)) is True

    non_git = tmp_path / "non_git_folder"
    non_git.mkdir()
    assert is_git_repository(str(non_git)) is False


def test_extract_commit_history(sample_git_repo: Path) -> None:
    """Verify commit extraction extracts metadata, authors, and diffs."""
    commits = extract_commit_history(str(sample_git_repo), max_commits=10)
    assert len(commits) == 2

    # Newest commit first
    latest = commits[0]
    assert latest.author_name == "Alice Engineer"
    assert latest.author_email == "alice@example.com"
    assert "Fix: Allow valid users to authenticate" in latest.message
    assert "auth.py" in latest.changed_files
    assert latest.diff_summary is not None
    assert "def authenticate(): return True" in latest.diff_summary

    # Oldest commit
    initial = commits[1]
    assert "Initial commit with basic auth" in initial.message
    assert "auth.py" in initial.changed_files


def test_commits_to_chunks(sample_git_repo: Path) -> None:
    """Verify commits are converted into CodeChunks with GIT_HISTORY type."""
    commits = extract_commit_history(str(sample_git_repo), max_commits=10)
    chunks = commits_to_chunks(commits, repository_id="repo-123")

    assert len(chunks) == 2
    for c in chunks:
        assert c.content_type == ContentType.GIT_HISTORY
        assert c.repository_id == "repo-123"
        assert c.commit_hash is not None
        assert c.commit_author == "Alice Engineer"
        assert c.commit_date is not None
        assert "Commit:" in c.content


def test_commit_registry_lifecycle() -> None:
    """Verify in-memory commit store, get, and delete operations."""
    repo_id = "test-registry-repo"
    dummy_commits = [
        GitCommitInfo(
            hash="1234567890abcdef",
            short_hash="12345678",
            author_name="Bob",
            author_email="bob@example.com",
            date="2026-04-01T12:00:00",
            message="Add feature",
        )
    ]

    store_commits(repo_id, dummy_commits)
    retrieved = get_stored_commits(repo_id)
    assert len(retrieved) == 1
    assert retrieved[0].author_name == "Bob"

    delete_stored_commits(repo_id)
    assert get_stored_commits(repo_id) == []
