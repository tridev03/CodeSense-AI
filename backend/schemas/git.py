"""
Pydantic schemas for Git Intelligence operations.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class GitCommitItem(BaseModel):
    """Details of a single Git commit."""
    hash: str
    short_hash: str
    author_name: str
    author_email: str
    date: str
    message: str
    changed_files: List[str] = Field(default_factory=list)
    diff_summary: Optional[str] = None


class GitCommitsResponse(BaseModel):
    """Response containing a paginated list of Git commits."""
    repository_id: str
    total_commits: int
    commits: List[GitCommitItem]


class GitSearchRequest(BaseModel):
    """Payload for searching Git commit history and diffs."""
    query: str = Field(..., min_length=1, description="Question or keyword about past changes")
    top_k: int = Field(default=10, ge=1, le=50, description="Max commits to return")
    author: Optional[str] = Field(None, description="Filter by commit author name or email")
    file_path: Optional[str] = Field(None, description="Filter by modified file path")


class GitSearchItem(BaseModel):
    """A matched commit chunk result."""
    chunk_id: str
    commit_hash: Optional[str] = None
    commit_author: Optional[str] = None
    commit_date: Optional[str] = None
    file_path: str
    content: str
    score: float


class GitSearchResponse(BaseModel):
    """Response returned by the Git search endpoint."""
    query: str
    repository_id: str
    total_results: int
    results: List[GitSearchItem]


class GitFileHistoryRequest(BaseModel):
    """Payload to query historical changes to a specific file."""
    file_path: str = Field(..., min_length=1, description="Relative path of file to inspect")
    top_k: int = Field(default=20, ge=1, le=100, description="Max commits to return")


class GitFileHistoryResponse(BaseModel):
    """Historical commits that modified a specific file."""
    file_path: str
    repository_id: str
    total_commits: int
    commits: List[GitCommitItem]
