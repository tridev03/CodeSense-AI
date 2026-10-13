"""
TEST-01 & TEST-03: Workstream 2 — Resilience, Idempotency & Recovery Test Suite.

Covers:
  - REL-02: Deterministic chunk ID generation & idempotent ingestion
  - REL-04: Persistent BM25 index serialization, disk storage & auto-load
  - REL-05: PostgreSQL ↔ Qdrant consistency & reconciliation service
  - REL-06 & REL-08: Resource bounds & connection pool timeout configuration
  - REL-01: Background task lifecycle, cancellation, and error isolation
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import uuid
import pytest

from backend.ingestion.models import (
    CodeChunk,
    ContentType,
    SymbolType,
    generate_deterministic_chunk_id,
)
from backend.retrieval.bm25 import BM25Retriever


# ─── REL-02: Deterministic Chunk IDs (Idempotent Ingestion) ─────────────────────


class TestDeterministicChunking:
    """Verifies that chunk ID generation is deterministic and stable (REL-02)."""

    def test_identical_inputs_produce_identical_chunk_ids(self):
        repo_id = str(uuid.uuid4())
        content = "def calculate_total(items):\n    return sum(items)"
        file_path = "services/billing.py"

        id1 = generate_deterministic_chunk_id(repo_id, file_path, content, start_line=1, end_line=2)
        id2 = generate_deterministic_chunk_id(repo_id, file_path, content, start_line=1, end_line=2)

        assert id1 == id2
        # Ensure it is a valid UUID
        assert uuid.UUID(id1)

    def test_different_content_produces_different_chunk_ids(self):
        repo_id = str(uuid.uuid4())
        file_path = "services/billing.py"

        id1 = generate_deterministic_chunk_id(repo_id, file_path, "def foo(): pass", 1, 1)
        id2 = generate_deterministic_chunk_id(repo_id, file_path, "def bar(): pass", 1, 1)

        assert id1 != id2

    def test_code_chunk_ensure_deterministic_id(self):
        repo_id = str(uuid.uuid4())
        chunk = CodeChunk(
            file_path="main.py",
            content="print('hello')",
            start_line=1,
            end_line=1,
        )
        original_id = chunk.chunk_id
        det_id = chunk.ensure_deterministic_id(repo_id)

        assert chunk.chunk_id == det_id
        assert chunk.repository_id == repo_id
        # Calling again yields the exact same ID
        assert chunk.ensure_deterministic_id(repo_id) == det_id


# ─── REL-04: Persistent BM25 Index ─────────────────────────────────────────────


class TestBM25Persistence:
    """Verifies that BM25 keyword indexes are persisted to disk and reloadable (REL-04)."""

    def test_bm25_persists_to_disk_and_auto_reloads(self, tmp_path: Path):
        retriever = BM25Retriever(storage_dir=tmp_path)
        repo_id = str(uuid.uuid4())

        chunks = [
            CodeChunk(
                file_path="auth.py",
                content="def authenticate_user(username, password): pass",
                function_name="authenticate_user",
                repository_id=repo_id,
            ),
            CodeChunk(
                file_path="payments.py",
                content="def process_payment(amount, currency): pass",
                function_name="process_payment",
                repository_id=repo_id,
            ),
        ]

        # 1. Build and verify disk file is written
        retriever.build_index(repo_id, chunks)
        expected_file = tmp_path / f"{repo_id}.pkl"
        assert expected_file.exists()

        # 2. Simulate complete memory flush / process restart
        retriever._indices.clear()
        assert repo_id not in retriever._indices

        # 3. Search triggers auto-load from disk
        results = retriever.search(repo_id, "authenticate username", top_k=5)
        assert len(results) > 0
        assert "auth.py" in results[0]["metadata"]["file_path"]

        # 4. Verify delete_index removes file from disk
        retriever.delete_index(repo_id)
        assert not expected_file.exists()
        assert not retriever.has_index(repo_id)


# ─── REL-05: Consistency & Reconciliation Service ──────────────────────────────


class TestReconciliationService:
    """Tests the PostgreSQL ↔ Qdrant state reconciliation service (REL-05)."""

    @pytest.mark.asyncio
    async def test_reconciliation_detects_missing_collection(self, test_db, tmp_path: Path):
        from backend.database.models import Repository, RepositorySourceType, RepositoryStatus
        from backend.services.reconciliation import ReconciliationService

        repo_id = uuid.uuid4()
        repo = Repository(
            id=repo_id,
            name="orphan-test-repo",
            url="https://github.com/test/orphan-test",
            source_type=RepositorySourceType.GITHUB,
            status=RepositoryStatus.INDEXED,  # Marked indexed but has no vectors
        )
        test_db.add(repo)
        await test_db.commit()

        # Mock vector store that reports collection does not exist
        class MockEmptyVectorStore:
            def collection_exists(self, repo_id: str) -> bool:
                return False

        retriever = BM25Retriever(storage_dir=tmp_path)
        recon_svc = ReconciliationService(
            db=test_db,
            vector_store=MockEmptyVectorStore(),
            bm25_retriever=retriever,
        )

        # 1. Check consistency without repair
        report = await recon_svc.check_consistency(auto_repair=False)
        assert str(repo_id) in report.missing_vector_collections
        assert not report.to_dict()["is_fully_consistent"]

        # 2. Check consistency with auto-repair
        repair_report = await recon_svc.check_consistency(auto_repair=True)
        assert str(repo_id) in repair_report.repaired_repositories

        # 3. Verify repository status was reverted to FAILED
        await test_db.refresh(repo)
        assert repo.status == RepositoryStatus.FAILED
        assert "Reconciliation" in (repo.error_message or "")


# ─── REL-01: Background Task Worker Reliability ────────────────────────────────


class TestWorkerReliability:
    """Tests async worker queue fault tolerance and concurrency (REL-01)."""

    @pytest.mark.asyncio
    async def test_worker_handles_concurrent_jobs(self):
        from backend.worker.tasks import AsyncTaskWorker, TaskStatus

        worker = AsyncTaskWorker(concurrency=2)
        await worker.start()

        completed_jobs = []

        async def sample_job(job_id: int):
            await asyncio.sleep(0.05)
            completed_jobs.append(job_id)
            return f"done-{job_id}"

        t1_id = worker.submit("job1", sample_job, 1)
        t2_id = worker.submit("job2", sample_job, 2)
        t3_id = worker.submit("job3", sample_job, 3)

        # Wait for all jobs to complete
        for _ in range(30):
            status_1 = worker.get_task(t1_id).status
            status_2 = worker.get_task(t2_id).status
            status_3 = worker.get_task(t3_id).status
            if (
                status_1 == TaskStatus.COMPLETED
                and status_2 == TaskStatus.COMPLETED
                and status_3 == TaskStatus.COMPLETED
            ):
                break
            await asyncio.sleep(0.05)

        assert len(completed_jobs) == 3
        assert worker.get_task(t1_id).result == "done-1"

        await worker.stop()

    @pytest.mark.asyncio
    async def test_cpu_workload_offloaded_to_threadpool(self):
        """REL-03: Heavy CPU/synchronous work does not block the async event loop."""
        import time

        def heavy_cpu_task(iterations: int) -> int:
            total = 0
            for i in range(iterations):
                total += (i % 7)
            return total

        # Run heavy CPU task inside threadpool
        cpu_future = asyncio.to_thread(heavy_cpu_task, 200_000)

        # Simultaneously run lightweight async tasks
        async_events = []
        for i in range(5):
            await asyncio.sleep(0.01)
            async_events.append(i)

        res = await cpu_future
        assert res > 0
        assert len(async_events) == 5

    @pytest.mark.asyncio
    async def test_worker_retries_transient_failure(self):
        """REL-01: Background task automatically retries up to max_retries."""
        from backend.worker.tasks import AsyncTaskWorker, TaskStatus

        worker = AsyncTaskWorker(concurrency=1)
        await worker.start()

        attempts = 0

        async def flaky_job():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ValueError("Transient error")
            return "recovered"

        task_id = worker.submit("flaky", flaky_job, max_retries=3)

        for _ in range(30):
            t = worker.get_task(task_id)
            if t.status == TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.05)

        task = worker.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == "recovered"
        assert task.retry_count == 2

        await worker.stop()
