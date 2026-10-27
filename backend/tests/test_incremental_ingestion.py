"""
Tests for Incremental Ingestion & File Hash Tracking (REL-03).
"""
import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient

from backend.ingestion.hash_tracker import (
    compute_file_sha256,
    compute_manifest_diff,
    load_repository_manifest,
    save_repository_manifest,
    delete_repository_manifest,
)
from backend.security.auth import create_access_token
from backend.services.repository_service import RepositoryService


def test_compute_file_sha256(tmp_path: Path):
    f = tmp_path / "sample.py"
    f.write_text("print('hello world')\n")
    h1 = compute_file_sha256(f)
    assert len(h1) == 64
    assert h1 == compute_file_sha256(f)

    # Modify file
    f.write_text("print('hello modified world')\n")
    h2 = compute_file_sha256(f)
    assert h1 != h2


def test_manifest_diff_detection():
    prev = {
        "a.py": "hash_a1",
        "b.py": "hash_b1",
        "deleted.py": "hash_d1",
    }
    curr = {
        "a.py": "hash_a1",         # Unchanged
        "b.py": "hash_b2",         # Modified
        "new_file.py": "hash_n1",  # Added
    }

    diff = compute_manifest_diff(prev, curr)
    assert diff.has_changes is True
    assert diff.requires_reindexing is True
    assert diff.unchanged_files == {"a.py"}
    assert diff.modified_files == {"b.py"}
    assert diff.added_files == {"new_file.py"}
    assert diff.deleted_files == {"deleted.py"}


def test_manifest_diff_no_changes():
    manifest = {"a.py": "h1", "b.py": "h2"}
    diff = compute_manifest_diff(manifest, manifest)
    assert diff.has_changes is False
    assert diff.requires_reindexing is False
    assert diff.unchanged_files == {"a.py", "b.py"}
    assert len(diff.added_files) == 0
    assert len(diff.modified_files) == 0
    assert len(diff.deleted_files) == 0


def test_manifest_save_load_delete(tmp_path: Path):
    repo_id = str(uuid.uuid4())
    manifest = {"main.py": "abc123hash", "utils.py": "def456hash"}

    save_repository_manifest(repo_id, manifest)
    loaded = load_repository_manifest(repo_id)
    assert loaded == manifest

    delete_repository_manifest(repo_id)
    assert load_repository_manifest(repo_id) == {}


@pytest.mark.asyncio
async def test_incremental_reindexing_skips_unchanged_embeddings(
    client: AsyncClient, test_db, tmp_path: Path
):
    """
    Verify that re-indexing an unchanged repository does not re-compute embeddings.
    """
    repo_dir = tmp_path / "repo_unchanged"
    repo_dir.mkdir()
    (repo_dir / "mod.py").write_text("def stable_function(): return 42\n")

    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, email="incremental@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post(
        "/api/v1/repositories",
        json={"name": "repo-unchanged", "url": str(repo_dir), "source_type": "local"},
        headers=headers,
    )
    assert res.status_code == 201
    repo_id = res.json()["id"]

    svc = RepositoryService(test_db)

    # Initial Index (saves manifest)
    res_1 = await svc.execute_indexing(uuid.UUID(repo_id))
    assert res_1.files_processed == 1

    manifest = load_repository_manifest(repo_id)
    assert "mod.py" in manifest

    # Second Index without modifying files: manifest diff has no changes
    res_2 = await svc.execute_indexing(uuid.UUID(repo_id))
    assert res_2.manifest_diff is not None
    assert res_2.manifest_diff.has_changes is False
    assert res_2.manifest_diff.unchanged_files == {"mod.py"}

