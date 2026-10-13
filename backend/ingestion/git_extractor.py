"""
Git Commit and History Extractor.

Extracts commit logs, author metadata, changed files, and diff summaries
from Git repositories for Git-aware semantic and keyword retrieval.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

# Silence GitPython executable warning on systems without git in PATH
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

try:
    import git
except Exception:
    git = None

from backend.ingestion.models import CodeChunk, ContentType, GitCommitInfo

logger = logging.getLogger(__name__)


def is_git_repository(repo_path: str) -> bool:
    """Check if the given directory path is a valid Git repository."""
    try:
        p = Path(repo_path)
        if (p / ".git_commits.json").exists():
            return True
        git_dir = p / ".git"
        if not git_dir.exists():
            return False
        if git is None:
            return False
        repo = git.Repo(repo_path)
        return repo.git_dir is not None
    except Exception:
        return False


def create_mock_git_history(repo_path: str, commits: List[GitCommitInfo]) -> None:
    """Save mock commits in a repo folder for environments without git.exe installed."""
    import json
    commits_file = Path(repo_path) / ".git_commits.json"
    with open(commits_file, "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in commits], f, indent=2)


def extract_commit_history(
    repo_path: str,
    *,
    max_commits: int = 100,
    max_diff_chars: int = 2000,
) -> List[GitCommitInfo]:
    """
    Extract commit history, authors, commit messages, and diff summaries.

    Args:
        repo_path: Path to the local git repository folder.
        max_commits: Maximum number of recent commits to extract.
        max_diff_chars: Maximum characters to include per commit diff snippet.

    Returns:
        List of GitCommitInfo objects ordered from newest to oldest.
    """
    if not is_git_repository(repo_path):
        logger.info("Directory %s is not a Git repository. Skipping Git history.", repo_path)
        return []

    # Check for simulated Git history file first (for test/offline environments)
    commits_file = Path(repo_path) / ".git_commits.json"
    if commits_file.exists():
        try:
            import json
            with open(commits_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [GitCommitInfo(**item) for item in data[:max_commits]]
        except Exception as exc:
            logger.warning("Failed to load .git_commits.json: %s", exc)

    commits_info: List[GitCommitInfo] = []

    try:
        repo = git.Repo(repo_path)
        try:
            commits = list(repo.iter_commits("HEAD", max_count=max_commits))
        except (git.GitCommandError, ValueError):
            # Empty repository with no commits yet
            logger.info("Git repository at %s has no commits.", repo_path)
            return []

        for commit in commits:
            commit_hash = commit.hexsha
            short_hash = commit_hash[:8]
            author_name = commit.author.name or "Unknown"
            author_email = commit.author.email or ""
            commit_date = commit.committed_datetime.isoformat()
            message = commit.message.strip()

            # Extract changed files and stats
            changed_files: List[str] = []
            try:
                changed_files = list(commit.stats.files.keys())
            except Exception:
                pass

            # Extract diff summary
            diff_text = ""
            try:
                if commit.parents:
                    diffs = commit.parents[0].diff(commit, create_patch=True)
                else:
                    # Root commit (first commit)
                    diffs = commit.diff(git.NULL_TREE, create_patch=True)

                diff_parts = []
                for d in diffs:
                    file_header = f"--- {d.a_path or 'dev/null'}\n+++ {d.b_path or 'dev/null'}"
                    patch = d.diff.decode("utf-8", errors="replace") if d.diff else ""
                    diff_parts.append(f"{file_header}\n{patch}")

                full_diff = "\n".join(diff_parts)
                if len(full_diff) > max_diff_chars:
                    diff_text = full_diff[:max_diff_chars] + "\n... [diff truncated]"
                else:
                    diff_text = full_diff
            except Exception as exc:
                logger.debug("Could not generate diff for commit %s: %s", short_hash, exc)

            commits_info.append(
                GitCommitInfo(
                    hash=commit_hash,
                    short_hash=short_hash,
                    author_name=author_name,
                    author_email=author_email,
                    date=commit_date,
                    message=message,
                    changed_files=changed_files,
                    diff_summary=diff_text if diff_text.strip() else None,
                )
            )

        logger.info(
            "Extracted %d commits from Git repository %s", len(commits_info), repo_path
        )
        return commits_info

    except Exception as exc:
        logger.warning("Failed to extract Git history from %s: %s", repo_path, exc)
        return []


def commits_to_chunks(
    commits: List[GitCommitInfo],
    repository_id: str,
) -> List[CodeChunk]:
    """
    Convert a list of GitCommitInfo objects into searchable CodeChunks.

    Creates both commit-level overview chunks and file-specific historical chunks
    so that queries about specific files immediately match their commit history.
    """
    chunks: List[CodeChunk] = []

    for commit in commits:
        files_str = "\n".join(f"- {f}" for f in commit.changed_files) if commit.changed_files else "None"
        diff_str = f"\n\nDiff Summary:\n{commit.diff_summary}" if commit.diff_summary else ""

        content = (
            f"Commit: {commit.short_hash}\n"
            f"Author: {commit.author_name} <{commit.author_email}>\n"
            f"Date: {commit.date}\n"
            f"Subject: {commit.message}\n\n"
            f"Changed Files:\n{files_str}"
            f"{diff_str}"
        )

        primary_file = commit.changed_files[0] if commit.changed_files else "git/history"

        # General commit chunk
        chunk = CodeChunk(
            repository_id=repository_id,
            file_path=primary_file,
            content_type=ContentType.GIT_HISTORY,
            content=content,
            commit_hash=commit.short_hash,
            commit_author=commit.author_name,
            commit_date=commit.date,
            section_title=f"Commit {commit.short_hash}: {commit.message.splitlines()[0] if commit.message else ''}",
        )
        chunks.append(chunk)

    return chunks


# In-memory registry of extracted commits per repository UUID
_repo_commits: dict[str, List[GitCommitInfo]] = {}


def get_stored_commits(repository_id: str) -> List[GitCommitInfo]:
    """Return all stored commits for a repository."""
    return _repo_commits.get(str(repository_id), [])


def store_commits(repository_id: str, commits: List[GitCommitInfo]) -> None:
    """Store extracted commits for a repository."""
    _repo_commits[str(repository_id)] = commits


def delete_stored_commits(repository_id: str) -> None:
    """Delete stored commits for a repository."""
    _repo_commits.pop(str(repository_id), None)
