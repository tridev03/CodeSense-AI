"""
Integration tests for the end-to-end repository ingestion pipeline.

Tests:
- End-to-end ingestion on a local multi-language mock repository
- IngestionResult statistics (files discovered, processed, chunks created)
- Code and documentation chunk generation
- RepositoryService execute_indexing pipeline execution with DB updates
"""
from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import IndexingJobStatus, RepositoryStatus
from backend.ingestion.models import ContentType, SymbolType
from backend.ingestion.pipeline import run_ingestion
from backend.schemas.repository import RepositoryCreate
from backend.services.repository_service import RepositoryService


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a realistic sample repository on disk for testing."""
    # 1. Python source file with Class and Function
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    python_code = '''import os
from typing import Optional

class DatabaseConnection:
    """Manages database connection pool."""

    def __init__(self, host: str, port: int = 5432):
        self.host = host
        self.port = port

    def connect(self) -> bool:
        """Establish database connection."""
        return True

def health_check() -> str:
    """Return database health status."""
    return "ok"
'''
    (src_dir / "db.py").write_text(python_code, encoding="utf-8")

    # 2. TypeScript component
    ts_code = '''export interface ButtonProps {
    label: string;
    onClick: () => void;
}

export const Button = (props: ButtonProps) => {
    return props.label;
};
'''
    (src_dir / "Button.tsx").write_text(ts_code, encoding="utf-8")

    # 3. Documentation
    readme_content = '''# Sample Knowledge Base

A test repository for verifying Phase 2 ingestion.

## Features
- Database connection pooling
- UI Button component

## Installation
Run `pip install -r requirements.txt`
'''
    (tmp_path / "README.md").write_text(readme_content, encoding="utf-8")

    # 4. Configuration
    config_content = '''{
  "name": "sample-repo",
  "version": "1.0.0"
}'''
    (tmp_path / "package.json").write_text(config_content, encoding="utf-8")

    # 5. Ignored directory (.git)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")

    return tmp_path


def test_run_ingestion_on_sample_repo(sample_repo: Path) -> None:
    """Verify run_ingestion correctly scans, parses, and chunks a multi-language repo."""
    result = run_ingestion(
        str(sample_repo),
        is_local=True,
        repository_id="test-repo-uuid",
    )

    assert result.files_discovered == 4  # db.py, Button.tsx, README.md, package.json
    assert result.files_processed == 4
    assert result.files_failed == 0
    assert result.total_chunks >= 4

    # Check that code chunks exist
    code_chunks = [c for c in result.chunks if c.content_type == ContentType.CODE]
    assert len(code_chunks) >= 2

    # Verify python function chunk
    db_method = next(
        (c for c in code_chunks if c.function_name == "connect"), None
    )
    assert db_method is not None
    assert db_method.class_name == "DatabaseConnection"
    assert db_method.file_path == "src/db.py"

    # Verify documentation chunks
    doc_chunks = [c for c in result.chunks if c.content_type == ContentType.DOCUMENTATION]
    assert len(doc_chunks) >= 2
    doc_titles = [c.section_title for c in doc_chunks]
    assert any("Sample Knowledge Base" in (t or "") or "Features" in (t or "") for t in doc_titles)

    # Verify config chunks
    config_chunks = [c for c in result.chunks if c.content_type == ContentType.CONFIGURATION]
    assert len(config_chunks) == 1
    assert config_chunks[0].file_path == "package.json"


@pytest.mark.asyncio
async def test_repository_service_execute_indexing(
    test_db: AsyncSession, sample_repo: Path
) -> None:
    """Verify RepositoryService.execute_indexing updates DB job and repo state correctly."""
    service = RepositoryService(test_db)

    # Register local repo
    repo = await service.create_repository(
        RepositoryCreate(
            url=str(sample_repo),
            name="Sample Test Repo",
        )
    )

    # Trigger indexing job
    job = await service.trigger_indexing(repo.id)
    assert job.status == IndexingJobStatus.PENDING

    # Execute indexing
    result = await service.execute_indexing(repo.id, job.id)

    assert result.total_chunks > 0
    assert result.files_processed == 4

    # Verify updated DB states
    updated_repo = await service.get_repository(repo.id)
    assert updated_repo.status == RepositoryStatus.INDEXED
    assert updated_repo.file_count == 4
    assert updated_repo.chunk_count == result.total_chunks

    latest_job = await service.get_indexing_status(repo.id)
    assert latest_job is not None
    assert latest_job.status == IndexingJobStatus.COMPLETED
    assert latest_job.progress == 100.0
    assert latest_job.files_processed == 4
    assert latest_job.chunks_created == result.total_chunks

