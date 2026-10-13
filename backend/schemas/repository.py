"""
Pydantic schemas for the Repository and IndexingJob API layer.

Schemas are strictly separate from ORM models:
- ORM models describe the database shape.
- Schemas describe the API contract (what clients send and receive).

`model_config = ConfigDict(from_attributes=True)` enables
`Schema.model_validate(orm_instance)` without manual mapping.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─── Enumerations ─────────────────────────────────────────────────────────────


class RepositoryStatus(str, Enum):
    PENDING = "pending"
    CLONING = "cloning"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class RepositorySourceType(str, Enum):
    GITHUB = "github"
    LOCAL = "local"


class IndexingJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ─── Repository ───────────────────────────────────────────────────────────────


class RepositoryCreate(BaseModel):
    """
    Request body for POST /repositories.

    Accepted URL formats:
    - GitHub HTTPS: https://github.com/owner/repo
    - Absolute local path: /home/user/my-project  or  C:\\Users\\me\\project
    """

    url: str = Field(
        ...,
        description="GitHub HTTPS URL or absolute local filesystem path",
        examples=["https://github.com/tiangolo/fastapi"],
        min_length=1,
    )
    name: Optional[str] = Field(
        None,
        description="Display name. Defaults to the repository slug if omitted.",
        max_length=255,
    )
    description: Optional[str] = Field(None, max_length=1000)
    branch: str = Field(
        default="main",
        max_length=255,
        description="Branch to index. Ignored for local paths.",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("URL cannot be empty.")

        # Absolute local paths (Unix or Windows)
        if v.startswith("/") or (len(v) > 2 and v[1] == ":" and v[2] in ("/", "\\")):
            return v

        # Remote Git URLs validated via GitUrlValidator (SEC-04, SEC-05)
        try:
            from backend.security.validators import GitUrlValidator
            validator = GitUrlValidator(check_ssrf=False)  # SSRF resolution check runs on actual clone
            return validator.validate(v)
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Branch name cannot be empty.")
        return v


class RepositoryResponse(BaseModel):
    """Full repository object returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    url: str
    source_type: RepositorySourceType
    branch: Optional[str]
    commit_hash: Optional[str]
    status: RepositoryStatus
    error_message: Optional[str]
    file_count: Optional[int]
    chunk_count: Optional[int]
    created_at: datetime
    updated_at: datetime


class RepositoryListResponse(BaseModel):
    """Paginated list of repositories."""

    items: List[RepositoryResponse]
    total: int
    skip: int = 0
    limit: int = 20


# ─── IndexingJob ──────────────────────────────────────────────────────────────


class IndexingJobResponse(BaseModel):
    """Indexing job status returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    status: IndexingJobStatus
    progress: float = Field(..., ge=0.0, le=100.0)
    current_step: Optional[str]
    error_message: Optional[str]
    files_processed: int
    files_total: int
    chunks_created: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class IndexTriggerResponse(BaseModel):
    """Response when indexing is triggered via POST /repositories/{id}/index."""

    job_id: uuid.UUID
    repository_id: uuid.UUID
    message: str
