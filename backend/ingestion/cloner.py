"""
Repository cloner: fetches repositories from GitHub or loads local paths.

Design decisions:
- Uses GitPython for cloning (proven, handles auth, progress, errors well).
- Shallow clones (depth=1) by default for speed and disk savings.
- For local repos, validates the path exists and is a valid directory.
- Security: rejects relative paths, path traversal, and non-absolute paths.
- Stores cloned repos under REPOS_STORAGE_PATH/<uuid>/.
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from backend.config.settings import settings

logger = logging.getLogger(__name__)


class ClonerError(Exception):
    """Base exception for repository cloning/loading errors."""


class CloneResult:
    """Result of a clone or load operation."""

    def __init__(
        self,
        local_path: str,
        is_cloned: bool,
        branch: Optional[str] = None,
        commit_hash: Optional[str] = None,
    ):
        self.local_path = local_path
        self.is_cloned = is_cloned    # True=cloned, False=local reference
        self.branch = branch
        self.commit_hash = commit_hash

    def __repr__(self) -> str:
        return (
            f"CloneResult(local_path={self.local_path!r}, "
            f"is_cloned={self.is_cloned}, branch={self.branch!r})"
        )


def _validate_github_url(url: str) -> None:
    """Validate that the URL is a legitimate GitHub HTTPS URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ClonerError(f"Only HTTPS GitHub URLs are supported, got: {url}")
    if "github.com" not in parsed.hostname:
        raise ClonerError(f"Only GitHub repositories are supported, got: {url}")
    # Must have at least /owner/repo
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(path_parts) < 2:
        raise ClonerError(
            f"GitHub URL must include owner and repo: {url}"
        )


def _validate_local_path(path: str) -> str:
    """
    Validate and resolve a local filesystem path.

    Security checks:
    - Must be absolute
    - Must exist
    - Must be a directory
    - Resolved (no symlink/traversal tricks)
    """
    p = Path(path)
    if not p.is_absolute():
        raise ClonerError(f"Local path must be absolute: {path}")

    resolved = p.resolve()
    if not resolved.exists():
        raise ClonerError(f"Local path does not exist: {path}")
    if not resolved.is_dir():
        raise ClonerError(f"Local path is not a directory: {path}")

    return str(resolved)


def clone_repository(
    url: str,
    *,
    branch: Optional[str] = "main",
    target_dir: Optional[str] = None,
    shallow: bool = True,
) -> CloneResult:
    """
    Clone a GitHub repository to local storage.

    Args:
        url: GitHub HTTPS URL (e.g. https://github.com/owner/repo).
        branch: Branch to clone. Defaults to 'main'.
        target_dir: Override the clone destination. If None, uses
                     REPOS_STORAGE_PATH/<uuid>.
        shallow: Use depth=1 for speed (default True).

    Returns:
        CloneResult with the local path and commit hash.

    Raises:
        ClonerError: On invalid URL, clone failure, or git errors.
    """
    try:
        import git
    except ImportError:
        raise ClonerError(
            "GitPython is required for cloning. Install with: pip install gitpython"
        )

    _validate_github_url(url)

    if target_dir is None:
        storage = Path(settings.REPOS_STORAGE_PATH).resolve()
        storage.mkdir(parents=True, exist_ok=True)
        target_dir = str(storage / str(uuid.uuid4()))

    target = Path(target_dir)
    if target.exists():
        shutil.rmtree(str(target))

    logger.info("Cloning repository: url=%s branch=%s target=%s", url, branch, target)

    try:
        clone_kwargs = {
            "url": url,
            "to_path": str(target),
        }
        if branch:
            clone_kwargs["branch"] = branch
        if shallow:
            clone_kwargs["depth"] = 1

        # Use GitHub token for authentication if available
        env = {}
        if settings.GITHUB_TOKEN:
            # Git credential via GIT_ASKPASS is cleaner than embedding in URL
            env["GIT_TERMINAL_PROMPT"] = "0"
            # Embed token in URL for HTTPS auth
            if "github.com" in url:
                parsed = urlparse(url)
                authed_url = f"{parsed.scheme}://x-access-token:{settings.GITHUB_TOKEN}@{parsed.hostname}{parsed.path}"
                clone_kwargs["url"] = authed_url

        try:
            repo = git.Repo.clone_from(**clone_kwargs)
        except git.GitCommandError as exc:
            err_msg = str(exc.stderr or exc)
            if branch and ("Remote branch" in err_msg or "Could not find remote branch" in err_msg):
                logger.warning(
                    "Branch '%s' not found for %s, falling back to remote default branch: %s",
                    branch, url, err_msg
                )
                if target.exists():
                    shutil.rmtree(str(target))
                clone_kwargs.pop("branch", None)
                repo = git.Repo.clone_from(**clone_kwargs)
            else:
                raise

        commit_hash = str(repo.head.commit.hexsha)
        try:
            active_branch = str(repo.active_branch)
        except TypeError:
            active_branch = branch or "HEAD"

        logger.info(
            "Clone completed: commit=%s branch=%s",
            commit_hash[:8],
            active_branch,
        )

        return CloneResult(
            local_path=str(target),
            is_cloned=True,
            branch=active_branch,
            commit_hash=commit_hash,
        )

    except git.GitCommandError as exc:
        # Clean up partial clone
        if target.exists():
            shutil.rmtree(str(target))
        raise ClonerError(f"Git clone failed: {exc.stderr or exc}") from exc
    except Exception as exc:
        if target.exists():
            shutil.rmtree(str(target))
        raise ClonerError(f"Unexpected error during clone: {exc}") from exc


def load_local_repository(path: str) -> CloneResult:
    """
    Load a local repository directory.

    This does NOT copy the directory — it returns a reference to the
    original path. The scanner will read files directly from there.

    Args:
        path: Absolute path to a local directory.

    Returns:
        CloneResult pointing to the local path.

    Raises:
        ClonerError: If the path is invalid or inaccessible.
    """
    resolved = _validate_local_path(path)

    # Try to read git info if it's a git repository
    commit_hash = None
    branch = None
    try:
        import git
        repo = git.Repo(resolved)
        commit_hash = str(repo.head.commit.hexsha)
        if not repo.head.is_detached:
            branch = str(repo.active_branch)
    except Exception:
        # Not a git repo or git not available — that's fine
        pass

    logger.info("Local repository loaded: path=%s", resolved)

    return CloneResult(
        local_path=resolved,
        is_cloned=False,
        branch=branch,
        commit_hash=commit_hash,
    )


def cleanup_clone(local_path: str) -> None:
    """
    Remove a cloned repository directory.

    Only removes directories under REPOS_STORAGE_PATH for safety.
    """
    target = Path(local_path).resolve()
    storage = Path(settings.REPOS_STORAGE_PATH).resolve()

    # Safety: only delete if it's under our storage directory
    try:
        target.relative_to(storage)
    except ValueError:
        logger.warning(
            "Refusing to delete path outside storage: %s", target
        )
        return

    if target.exists():
        shutil.rmtree(str(target))
        logger.info("Cleaned up cloned repository: %s", target)

