"""
Repository service: business logic for the repository lifecycle.

This layer sits between API routes (thin, HTTP-focused) and CRUD functions
(thin, DB-focused). All orchestration, validation, and domain rules live here.

Service methods raise typed exceptions that routes map to HTTP status codes.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import crud
from backend.database.models import (
    IndexingJob,
    IndexingJobStatus,
    Repository,
    RepositorySourceType,
    RepositoryStatus,
)
from backend.schemas.repository import RepositoryCreate

logger = logging.getLogger(__name__)


# ─── Domain Exceptions ────────────────────────────────────────────────────────


class RepositoryAlreadyExistsError(Exception):
    """A repository with the same URL is already registered."""


class RepositoryNotFoundError(Exception):
    """The requested repository does not exist."""


class IndexingAlreadyRunningError(Exception):
    """An indexing job for this repository is currently in progress."""


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _extract_repo_name(url: str) -> str:
    """
    Derive a human-readable display name from a URL or path.

    Examples:
        https://github.com/tiangolo/fastapi  →  "tiangolo/fastapi"
        https://github.com/tiangolo/fastapi.git  →  "tiangolo/fastapi"
        /home/user/my-project  →  "my-project"
        C:\\Users\\me\\project  →  "project"
    """
    url = url.rstrip("/").rstrip("\\")
    if "github.com" in url:
        # Extract "owner/repo" portion
        tail = url.split("github.com/", 1)[-1]
        tail = tail.removesuffix(".git")
        parts = [p for p in tail.split("/") if p]
        return "/".join(parts[:2]) if len(parts) >= 2 else tail
    # Local path
    return url.replace("\\", "/").split("/")[-1]


def _detect_source_type(url: str) -> RepositorySourceType:
    if "github.com" in url:
        return RepositorySourceType.GITHUB
    return RepositorySourceType.LOCAL


# ─── Service ──────────────────────────────────────────────────────────────────


class RepositoryService:
    """
    Encapsulates all business operations on Repository entities.

    Each method operates within the session provided at construction time.
    The caller (the API route) is responsible for the session lifecycle.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_repository(
        self, payload: RepositoryCreate, owner_id: Optional[uuid.UUID] = None
    ) -> Repository:
        """
        Register a new repository.

        Does NOT start indexing — that is a separate explicit action.

        Args:
            payload: Repository creation payload.
            owner_id: UUID of the user creating the repository (SEC-02).

        Raises:
            RepositoryAlreadyExistsError: if the URL is already registered.
        """
        existing = await crud.get_repository_by_url(self._db, payload.url)
        if existing is not None:
            raise RepositoryAlreadyExistsError(
                f"A repository with URL '{payload.url}' already exists "
                f"(id={existing.id})."
            )

        name = payload.name or _extract_repo_name(payload.url)
        source_type = _detect_source_type(payload.url)

        repo = await crud.create_repository(
            self._db,
            name=name,
            url=payload.url,
            source_type=source_type,
            branch=payload.branch,
            description=payload.description,
            owner_id=owner_id,
        )
        await self._db.commit()
        logger.info(
            "Repository registered",
            extra={"repository_id": str(repo.id), "repo_name": repo.name},
        )
        return repo

    async def get_repository(self, repository_id: uuid.UUID) -> Repository:
        """
        Fetch a repository by ID.

        Raises:
            RepositoryNotFoundError: if no repository exists with that ID.
        """
        repo = await crud.get_repository(self._db, repository_id)
        if repo is None:
            raise RepositoryNotFoundError(
                f"Repository with id={repository_id} not found."
            )
        return repo

    async def list_repositories(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        owner_id: Optional[uuid.UUID] = None,
    ) -> Tuple[Sequence[Repository], int]:
        """
        Return a paginated list of repositories and the total count.

        When owner_id is provided, only that user's repositories are returned (SEC-02).
        Superusers should pass owner_id=None to list all repositories.
        """
        if owner_id is not None:
            repos = await crud.list_repositories_for_user(
                self._db, owner_id, skip=skip, limit=limit
            )
            total = await crud.count_repositories_for_user(self._db, owner_id)
        else:
            repos = await crud.list_repositories(self._db, skip=skip, limit=limit)
            total = await crud.count_repositories(self._db)
        return repos, total

    async def delete_repository(self, repository_id: uuid.UUID) -> None:
        """
        Delete a repository and all associated data (cascade).

        Raises:
            RepositoryNotFoundError: if no repository exists with that ID.
        """
        await self.get_repository(repository_id)  # raises if not found
        await crud.delete_repository(self._db, repository_id)
        await self._db.commit()

        # Delete Qdrant vector collection for this repository
        try:
            from backend.retrieval import VectorStoreService
            VectorStoreService().delete_collection(str(repository_id))
        except Exception as exc:
            logger.warning(
                "Could not delete vector collection for repo %s: %s",
                repository_id, exc,
            )

        # Delete BM25 index for this repository
        try:
            from backend.retrieval.hybrid import get_bm25_retriever
            get_bm25_retriever().delete_index(str(repository_id))
        except Exception as exc:
            logger.warning(
                "Could not delete BM25 index for repo %s: %s",
                repository_id, exc,
            )

        # Delete stored Git commits cache
        try:
            from backend.ingestion.git_extractor import delete_stored_commits
            delete_stored_commits(str(repository_id))
        except Exception as exc:
            logger.warning(
                "Could not delete stored Git commits for repo %s: %s",
                repository_id, exc,
            )

        logger.info(
            "Repository deleted", extra={"repository_id": str(repository_id)}
        )

    async def trigger_indexing(self, repository_id: uuid.UUID) -> IndexingJob:
        """
        Create an indexing job for a repository and execute the ingestion pipeline.

        Raises:
            RepositoryNotFoundError: if the repository does not exist.
        """
        await self.get_repository(repository_id)  # raises if not found

        # Update repository status to reflect it is queued
        await crud.update_repository_status(
            self._db, repository_id, status=RepositoryStatus.PENDING
        )

        job = await crud.create_indexing_job(
            self._db, repository_id=repository_id
        )
        await self._db.commit()

        logger.info(
            "Indexing job created",
            extra={
                "job_id": str(job.id),
                "repository_id": str(repository_id),
            },
        )
        return job

    async def execute_indexing(
        self, repository_id: uuid.UUID, job_id: Optional[uuid.UUID] = None
    ) -> IngestionResult:
        """
        Run the ingestion pipeline for a given repository and update DB records.

        Args:
            repository_id: UUID of the repository.
            job_id: Optional UUID of the indexing job.

        Returns:
            IngestionResult with all generated chunks and metrics.
        """
        from datetime import datetime
        from backend.ingestion.pipeline import run_ingestion

        repo = await self.get_repository(repository_id)

        if job_id is None:
            latest = await crud.get_latest_indexing_job(self._db, repository_id)
            if latest:
                job_id = latest.id
            else:
                new_job = await crud.create_indexing_job(self._db, repository_id=repository_id)
                job_id = new_job.id
        
        await crud.update_indexing_job(
            self._db,
            job_id,
            status=IndexingJobStatus.RUNNING,
            started_at=datetime.utcnow(),
            progress=5.0,
            current_step="Starting ingestion pipeline",
        )
        await self._db.commit()

        try:
            is_local = (repo.source_type == RepositorySourceType.LOCAL)
            # Step 1: Clone / Scan / Parse / Chunk
            await crud.update_indexing_job(
                self._db,
                job_id,
                progress=10.0,
                current_step="Cloning and analyzing repository structure",
            )
            await self._db.commit()

            try:
                result = await asyncio.to_thread(
                    run_ingestion,
                    repo.url,
                    is_local=is_local,
                    branch=repo.branch,
                    repository_id=str(repository_id),
                )
            except ClonerError as ce:
                raise RuntimeError(f"[CLONING_FAILED] {ce}") from ce
            except ValueError as ve:
                raise RuntimeError(f"[SCANNING_FAILED] {ve}") from ve
            except TimeoutError as te:
                raise RuntimeError(f"[TIMEOUT_EXCEEDED] {te}") from te

            commit_hash = result.clone_result.commit_hash if result.clone_result else None

            # Extract Git commit history if available
            from backend.ingestion.git_extractor import (
                commits_to_chunks,
                extract_commit_history,
                is_git_repository,
                store_commits,
            )

            repo_path = result.clone_result.local_path if result.clone_result else repo.url
            git_chunks = []
            if is_git_repository(repo_path):
                commits = await asyncio.to_thread(extract_commit_history, repo_path, max_commits=100)
                if commits:
                    store_commits(str(repository_id), commits)
                    if not commit_hash:
                        commit_hash = commits[0].hash
                    git_chunks = commits_to_chunks(commits, str(repository_id))

            all_chunks = list(result.chunks) + git_chunks

            # Embed and index chunks into Qdrant vector store
            if all_chunks:
                from backend.embeddings import get_embedding_service
                from backend.retrieval import VectorStoreService

                await crud.update_indexing_job(
                    self._db,
                    job_id,
                    progress=60.0,
                    current_step="Generating semantic embeddings",
                )
                await self._db.commit()

                emb_svc = get_embedding_service()
                vec_store = VectorStoreService()

                texts = [c.content for c in all_chunks]
                try:
                    embeddings = await asyncio.to_thread(emb_svc.embed_texts, texts)
                except Exception as ee:
                    raise RuntimeError(f"[EMBEDDING_FAILED] Failed to compute text embeddings: {ee}") from ee

                await crud.update_indexing_job(
                    self._db,
                    job_id,
                    progress=85.0,
                    current_step="Indexing vectors and BM25 lexicons",
                )
                await self._db.commit()

                try:
                    await asyncio.to_thread(vec_store.delete_collection, str(repository_id))
                    await asyncio.to_thread(vec_store.ensure_collection, str(repository_id))
                    await asyncio.to_thread(vec_store.upsert_chunks, str(repository_id), all_chunks, embeddings)
                except Exception as ve:
                    raise RuntimeError(f"[VECTOR_STORE_FAILED] Failed to persist vectors to Qdrant: {ve}") from ve

                # Build & persist BM25 keyword index for hybrid retrieval
                try:
                    from backend.retrieval.hybrid import get_bm25_retriever
                    bm25_retriever = get_bm25_retriever()
                    await asyncio.to_thread(bm25_retriever.delete_index, str(repository_id))
                    await asyncio.to_thread(bm25_retriever.build_index, str(repository_id), all_chunks)
                except Exception as be:
                    raise RuntimeError(f"[BM25_INDEX_FAILED] Failed to build lexical BM25 index: {be}") from be

            # Mark job as completed
            await crud.update_indexing_job(
                self._db,
                job_id,
                status=IndexingJobStatus.COMPLETED,
                progress=100.0,
                current_step="Ingestion and indexing complete",
                files_processed=result.files_processed,
                files_total=result.files_discovered,
                chunks_created=len(all_chunks),
                completed_at=datetime.utcnow(),
            )

            # Update repository state
            actual_branch = result.clone_result.branch if result.clone_result else None
            await crud.update_repository_status(
                self._db,
                repository_id,
                status=RepositoryStatus.INDEXED,
                file_count=result.files_processed,
                chunk_count=len(all_chunks),
                commit_hash=commit_hash,
                branch=actual_branch,
            )
            await self._db.commit()
            return result

        except Exception as exc:
            logger.exception("Ingestion failed for repository %s", repository_id)
            if 'result' in locals() and getattr(result, 'clone_result', None) and result.clone_result.is_cloned:
                try:
                    from backend.ingestion.cloner import cleanup_clone
                    cleanup_clone(result.clone_result.local_path)
                except Exception:
                    pass
            await crud.update_indexing_job(
                self._db,
                job_id,
                status=IndexingJobStatus.FAILED,
                error_message=str(exc),
                completed_at=datetime.utcnow(),
            )
            await crud.update_repository_status(
                self._db,
                repository_id,
                status=RepositoryStatus.FAILED,
                error_message=str(exc),
            )
            await self._db.commit()
            raise

    async def get_indexing_status(
        self, repository_id: uuid.UUID
    ) -> Optional[IndexingJob]:
        """
        Return the most recent indexing job for a repository, or None if never indexed.

        Raises:
            RepositoryNotFoundError: if the repository does not exist.
        """
        await self.get_repository(repository_id)  # raises if not found
        return await crud.get_latest_indexing_job(self._db, repository_id)

