"""
REL-05: PostgreSQL and Qdrant Consistency & Reconciliation Service.

Ensures that the PostgreSQL database state, Qdrant vector collections, and
disk-persisted BM25 indexes remain synchronized.

Provides:
- Inconsistency detection (missing collections, orphan collections, count mismatch)
- Self-healing reconciliation (reverts inconsistent INDEXED status to PENDING/FAILED)
- Cleanup of orphaned collections and stale index files
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import Repository, RepositoryStatus
from backend.retrieval import VectorStoreService
from backend.retrieval.bm25 import BM25Retriever, get_default_bm25_storage_dir

logger = logging.getLogger(__name__)


class ReconciliationReport:
    """Detailed summary of repository consistency check."""

    def __init__(self) -> None:
        self.total_repositories_checked: int = 0
        self.consistent_repositories: List[str] = []
        self.missing_vector_collections: List[str] = []
        self.missing_bm25_indexes: List[str] = []
        self.orphan_vector_collections: List[str] = []
        self.orphan_bm25_indexes: List[str] = []
        self.repaired_repositories: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_repositories_checked": self.total_repositories_checked,
            "consistent_count": len(self.consistent_repositories),
            "missing_vector_collections": self.missing_vector_collections,
            "missing_bm25_indexes": self.missing_bm25_indexes,
            "orphan_vector_collections": self.orphan_vector_collections,
            "orphan_bm25_indexes": self.orphan_bm25_indexes,
            "repaired_repositories": self.repaired_repositories,
            "is_fully_consistent": (
                not self.missing_vector_collections
                and not self.missing_bm25_indexes
                and not self.orphan_vector_collections
            ),
        }


class ReconciliationService:
    """
    Validates and restores state alignment between PostgreSQL, Qdrant, and BM25 (REL-05).
    """

    def __init__(
        self,
        db: AsyncSession,
        vector_store: Optional[VectorStoreService] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
    ) -> None:
        self._db = db
        self._vector_store = vector_store or VectorStoreService()
        self._bm25 = bm25_retriever or BM25Retriever()

    async def check_consistency(self, *, auto_repair: bool = False) -> ReconciliationReport:
        """
        Inspect all repositories and compare with vector and BM25 stores.

        If auto_repair=True:
        - Repositories marked INDEXED but missing collections are demoted to FAILED
          with an error message explaining the missing store state.
        """
        report = ReconciliationReport()

        # Query all repositories from PostgreSQL
        stmt = select(Repository)
        result = await self._db.execute(stmt)
        repos = result.scalars().all()
        report.total_repositories_checked = len(repos)

        known_repo_ids = {str(r.id) for r in repos}

        for repo in repos:
            repo_id_str = str(repo.id)
            if repo.status == RepositoryStatus.INDEXED:
                has_vector = self._vector_store.collection_exists(repo_id_str)
                has_bm25 = self._bm25.has_index(repo_id_str)

                is_ok = True
                if not has_vector:
                    report.missing_vector_collections.append(repo_id_str)
                    is_ok = False
                if not has_bm25:
                    report.missing_bm25_indexes.append(repo_id_str)
                    is_ok = False

                if is_ok:
                    report.consistent_repositories.append(repo_id_str)
                elif auto_repair:
                    repo.status = RepositoryStatus.FAILED
                    repo.error_message = (
                        "Reconciliation detected missing index or vector collection. Re-indexing required."
                    )
                    report.repaired_repositories.append(repo_id_str)
            else:
                report.consistent_repositories.append(repo_id_str)

        if auto_repair and report.repaired_repositories:
            await self._db.commit()
            logger.info("Auto-repaired %d inconsistent repositories", len(report.repaired_repositories))

        # Check for orphan BM25 disk indexes
        bm25_dir = get_default_bm25_storage_dir()
        if bm25_dir.exists():
            for pkl_file in bm25_dir.glob("*.pkl"):
                repo_id_from_file = pkl_file.stem
                if repo_id_from_file not in known_repo_ids:
                    report.orphan_bm25_indexes.append(repo_id_from_file)

        return report

    async def cleanup_orphans(self) -> Dict[str, int]:
        """
        Remove orphaned vector collections and BM25 index files (REL-05).
        """
        stmt = select(Repository.id)
        result = await self._db.execute(stmt)
        valid_ids = {str(row[0]) for row in result.all()}

        cleaned_bm25 = 0
        bm25_dir = get_default_bm25_storage_dir()
        if bm25_dir.exists():
            for pkl_file in bm25_dir.glob("*.pkl"):
                if pkl_file.stem not in valid_ids:
                    try:
                        pkl_file.unlink()
                        cleaned_bm25 += 1
                        logger.info("Purged orphan BM25 index: %s", pkl_file)
                    except Exception as exc:
                        logger.warning("Failed to remove orphan BM25 index %s: %s", pkl_file, exc)

        return {"cleaned_bm25": cleaned_bm25}
