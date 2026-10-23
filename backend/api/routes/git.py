"""
Git Intelligence API Endpoints.

Provides endpoints for inspecting Git commit logs, searching commit history
and diffs, and tracking historical changes to specific files.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_valid_repository
from backend.database.models import Repository
from backend.ingestion.git_extractor import get_stored_commits
from backend.retrieval.hybrid import HybridRetriever
from backend.schemas.git import (
    GitCommitItem,
    GitCommitsResponse,
    GitFileHistoryRequest,
    GitFileHistoryResponse,
    GitSearchItem,
    GitSearchRequest,
    GitSearchResponse,
)
from backend.services.repository_service import RepositoryNotFoundError

router = APIRouter(prefix="/repositories", tags=["git"])


@router.get(
    "/{repository_id}/git/commits",
    response_model=GitCommitsResponse,
    summary="List repository commit history",
    description="Returns stored Git commit history including hashes, authors, timestamps, and changed files.",
)
async def list_commits(
    repository_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    repo: Repository = Depends(get_valid_repository),
) -> GitCommitsResponse:
    commits = get_stored_commits(str(repository_id))
    items = [
        GitCommitItem(
            hash=c.hash,
            short_hash=c.short_hash,
            author_name=c.author_name,
            author_email=c.author_email,
            date=c.date,
            message=c.message,
            changed_files=c.changed_files,
            diff_summary=c.diff_summary,
        )
        for c in commits[:limit]
    ]
    return GitCommitsResponse(
        repository_id=str(repository_id),
        total_commits=len(commits),
        commits=items,
    )


@router.post(
    "/{repository_id}/git/search",
    response_model=GitSearchResponse,
    summary="Search Git commit messages and diffs",
    description="Performs semantic and keyword search restricted to Git commit history and diffs.",
)
async def search_git_history(
    repository_id: uuid.UUID,
    payload: GitSearchRequest,
    repo: Repository = Depends(get_valid_repository),
) -> GitSearchResponse:
    retriever = HybridRetriever()

    filters: Dict[str, Any] = {"content_type": "git_history"}
    if payload.author:
        filters["commit_author"] = payload.author

    hits = retriever.retrieve(
        repository_id=str(repository_id),
        query=payload.query,
        mode="hybrid",
        top_k=payload.top_k,
        filters=filters,
    )

    results: List[GitSearchItem] = []
    for hit in hits:
        meta = hit.get("metadata", {})
        file_path = meta.get("file_path", "")

        if payload.file_path and payload.file_path.lower() not in file_path.lower():
            continue

        results.append(
            GitSearchItem(
                chunk_id=hit.get("id", ""),
                commit_hash=meta.get("commit_hash"),
                commit_author=meta.get("commit_author"),
                commit_date=meta.get("commit_date"),
                file_path=file_path,
                content=hit.get("content", ""),
                score=float(hit.get("score", 0.0)),
            )
        )

    return GitSearchResponse(
        query=payload.query,
        repository_id=str(repository_id),
        total_results=len(results),
        results=results,
    )


@router.post(
    "/{repository_id}/git/file-history",
    response_model=GitFileHistoryResponse,
    summary="Query commit history for a specific file",
    description="Returns all commits that modified, created, or deleted a specific file.",
)
async def get_file_history(
    repository_id: uuid.UUID,
    payload: GitFileHistoryRequest,
    repo: Repository = Depends(get_valid_repository),
) -> GitFileHistoryResponse:
    commits = get_stored_commits(str(repository_id))
    normalized_target = payload.file_path.replace("\\", "/").lower()

    matching_commits = []
    for c in commits:
        for f in c.changed_files:
            if normalized_target in f.replace("\\", "/").lower():
                matching_commits.append(
                    GitCommitItem(
                        hash=c.hash,
                        short_hash=c.short_hash,
                        author_name=c.author_name,
                        author_email=c.author_email,
                        date=c.date,
                        message=c.message,
                        changed_files=c.changed_files,
                        diff_summary=c.diff_summary,
                    )
                )
                break

    return GitFileHistoryResponse(
        file_path=payload.file_path,
        repository_id=str(repository_id),
        total_commits=len(matching_commits),
        commits=matching_commits[:payload.top_k],
    )
