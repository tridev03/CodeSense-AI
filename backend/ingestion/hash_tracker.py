"""
Incremental ingestion hash tracking.

Computes SHA-256 digests for repository source files and manages repository
manifests to support idempotent incremental re-indexing (REL-03):
- Detects added, modified, deleted, and unchanged files.
- Purges chunks only for modified and deleted files.
- Re-embeds only modified and added files.
- Preserves chunks for unchanged files without re-embedding.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

from backend.config.settings import settings

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: Path | str) -> str:
    """Compute the SHA-256 hash of a file on disk."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found for hash computation: {file_path}")

    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while block := f.read(65536):
            hasher.update(block)
    return hasher.hexdigest()


def get_manifest_path(repository_id: str) -> Path:
    """Return the filesystem path for the repository file hash manifest."""
    storage_dir = Path(settings.REPOS_STORAGE_PATH)
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir / f"{repository_id}_manifest.json"


def load_repository_manifest(repository_id: str) -> Dict[str, str]:
    """
    Load previous file hash manifest for a repository.

    Returns:
        Mapping of relative file path -> SHA-256 digest string.
        Returns empty dict if no manifest exists.
    """
    manifest_path = get_manifest_path(repository_id)
    if not manifest_path.exists():
        return {}

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning("Could not read manifest at %s: %s", manifest_path, exc)
    return {}


def save_repository_manifest(repository_id: str, manifest: Dict[str, str]) -> None:
    """Save the file hash manifest for a repository."""
    manifest_path = get_manifest_path(repository_id)
    try:
        temp_path = manifest_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        temp_path.replace(manifest_path)
        logger.info("Saved manifest for repository %s (%d files)", repository_id, len(manifest))
    except Exception as exc:
        logger.error("Failed to save manifest at %s: %s", manifest_path, exc)


def delete_repository_manifest(repository_id: str) -> None:
    """Remove manifest file on repository deletion."""
    manifest_path = get_manifest_path(repository_id)
    try:
        if manifest_path.exists():
            manifest_path.unlink()
            logger.info("Deleted manifest for repository %s", repository_id)
    except Exception as exc:
        logger.warning("Could not delete manifest for %s: %s", repository_id, exc)


@dataclass(frozen=True)
class ManifestDiff:
    """Diff comparing previous indexing manifest against current scan."""
    added_files: Set[str] = field(default_factory=set)
    modified_files: Set[str] = field(default_factory=set)
    deleted_files: Set[str] = field(default_factory=set)
    unchanged_files: Set[str] = field(default_factory=set)

    @property
    def has_changes(self) -> bool:
        return bool(self.added_files or self.modified_files or self.deleted_files)

    @property
    def requires_reindexing(self) -> bool:
        return bool(self.added_files or self.modified_files)


def compute_manifest_diff(
    previous_manifest: Dict[str, str],
    current_manifest: Dict[str, str],
) -> ManifestDiff:
    """
    Compare previous file hashes with current file hashes to find deltas.
    """
    prev_keys = set(previous_manifest.keys())
    curr_keys = set(current_manifest.keys())

    added = curr_keys - prev_keys
    deleted = prev_keys - curr_keys
    common = prev_keys & curr_keys

    modified = {p for p in common if previous_manifest[p] != current_manifest[p]}
    unchanged = {p for p in common if previous_manifest[p] == current_manifest[p]}

    return ManifestDiff(
        added_files=added,
        modified_files=modified,
        deleted_files=deleted,
        unchanged_files=unchanged,
    )

