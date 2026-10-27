"""
Queue adapter test suite — REL-01 Part 2.

All tests are offline-safe (no real Redis required).
Redis-specific behaviour is tested using mocks so the CI pipeline
never needs a live Redis connection.

Tests cover:
  - LocalTaskQueue auto-selected when REDIS_URL is absent
  - LocalTaskQueue submit and status query
  - LocalTaskQueue falls back gracefully when celery is absent
  - RedisTaskQueue selected when REDIS_URL is set and dependencies present
  - RedisTaskQueue enqueues correctly (mocked Celery)
  - RedisTaskQueue maps all Celery states to unified status values
  - reset_task_queue clears the singleton (enabling mode-switching in tests)
  - TaskInfo dict shape is consistent across both modes
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ─── LocalTaskQueue ────────────────────────────────────────────────────────────


class TestLocalTaskQueue:
    """Tests for Mode A — in-process queue (no Redis required)."""

    def setup_method(self):
        """Reset singleton before each test."""
        from backend.worker.queue_adapter import reset_task_queue
        reset_task_queue()

    def test_get_task_queue_returns_local_when_no_redis_url(self, monkeypatch):
        """Without REDIS_URL, auto-detection must choose LocalTaskQueue."""
        monkeypatch.setattr(
            "backend.config.settings.settings.REDIS_URL", None
        )
        from backend.worker.queue_adapter import get_task_queue, LocalTaskQueue, reset_task_queue
        reset_task_queue()
        queue = get_task_queue()
        assert isinstance(queue, LocalTaskQueue)
        assert queue.mode == "local"

    def test_get_task_queue_respects_task_queue_mode_local(self, monkeypatch):
        """When TASK_QUEUE_MODE='local', LocalTaskQueue is used even with REDIS_URL configured."""
        monkeypatch.setattr(
            "backend.config.settings.settings.REDIS_URL", "redis://localhost:6379/0"
        )
        monkeypatch.setattr(
            "backend.config.settings.settings.TASK_QUEUE_MODE", "local"
        )
        from backend.worker.queue_adapter import get_task_queue, LocalTaskQueue, reset_task_queue
        reset_task_queue()
        queue = get_task_queue()
        assert isinstance(queue, LocalTaskQueue)
        assert queue.mode == "local"

    def test_get_task_queue_falls_back_to_local_when_celery_missing(self, monkeypatch):
        """Even if REDIS_URL is set, missing celery package → LocalTaskQueue."""
        monkeypatch.setattr(
            "backend.config.settings.settings.REDIS_URL", "redis://localhost:6379/0"
        )
        from backend.worker.queue_adapter import reset_task_queue
        reset_task_queue()

        with patch.dict("sys.modules", {"celery": None, "redis": None}):
            from backend.worker.queue_adapter import _build_queue, LocalTaskQueue
            queue = _build_queue()
            assert isinstance(queue, LocalTaskQueue)

    @pytest.mark.asyncio
    async def test_local_queue_submit_returns_task_id(self, monkeypatch):
        """LocalTaskQueue.submit_indexing_job returns a non-empty task_id string."""
        monkeypatch.setattr(
            "backend.config.settings.settings.REDIS_URL", None
        )
        from backend.worker.queue_adapter import LocalTaskQueue, reset_task_queue
        reset_task_queue()

        queue = LocalTaskQueue()

        # Mock RepositoryService.execute_indexing so no real DB is touched
        mock_execute = AsyncMock(return_value={"chunks": 10})

        with patch(
            "backend.worker.queue_adapter.uuid",
        ), patch(
            "backend.services.repository_service.RepositoryService.execute_indexing",
            mock_execute,
        ):
            task_id = await queue.submit_indexing_job("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        assert isinstance(task_id, str)
        assert len(task_id) > 10

    @pytest.mark.asyncio
    async def test_local_queue_get_task_info_returns_none_for_unknown(self):
        """Querying an unknown task_id returns None gracefully."""
        from backend.worker.queue_adapter import LocalTaskQueue
        queue = LocalTaskQueue()
        result = await queue.get_task_info("non-existent-task-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_local_queue_list_tasks_returns_list(self):
        """list_tasks returns a list (possibly empty)."""
        from backend.worker.queue_adapter import LocalTaskQueue
        queue = LocalTaskQueue()
        result = await queue.list_tasks(limit=10)
        assert isinstance(result, list)

    def test_task_info_has_mode_field_local(self):
        """TaskInfo dict from LocalTaskQueue always has mode='local'."""
        from backend.worker.tasks import AsyncTaskWorker
        import asyncio

        async def _dummy(): return "done"
        worker = AsyncTaskWorker(concurrency=1)
        # Directly inject a task into the worker's registry
        from backend.worker.tasks import BackgroundTask
        task = BackgroundTask(task_id="test-123", name="dummy", coro_fn=_dummy)
        worker._tasks["test-123"] = task

        from backend.worker.queue_adapter import LocalTaskQueue
        queue = LocalTaskQueue()

        # Patch get_task_worker in backend.worker.tasks
        with patch("backend.worker.tasks.get_task_worker", return_value=worker):
            result = asyncio.run(queue.get_task_info("test-123"))

        assert result is not None
        assert result["mode"] == "local"
        assert "status" in result
        assert "task_id" in result


# ─── RedisTaskQueue (mocked) ─────────────────────────────────────────────────


class TestRedisTaskQueue:
    """Tests for Mode B — Redis/Celery (all Celery calls are mocked)."""

    def _make_redis_queue(self) -> Any:
        """Return a RedisTaskQueue with a mocked Celery app."""
        mock_celery = MagicMock()
        with patch("backend.worker.queue_adapter.RedisTaskQueue.__init__") as mock_init:
            mock_init.return_value = None
            from backend.worker.queue_adapter import RedisTaskQueue
            queue = RedisTaskQueue.__new__(RedisTaskQueue)
            queue._celery = mock_celery
            queue.mode = "redis"
        return queue

    @pytest.mark.asyncio
    async def test_redis_queue_submit_returns_task_id(self):
        """RedisTaskQueue.submit_indexing_job calls send_task and returns celery task id."""
        queue = self._make_redis_queue()
        mock_result = MagicMock()
        mock_result.id = "celery-uuid-1234"
        queue._celery.send_task.return_value = mock_result

        task_id = await queue.submit_indexing_job("repo-uuid-abcd")

        queue._celery.send_task.assert_called_once_with(
            "backend.worker.celery_tasks.index_repository",
            args=["repo-uuid-abcd"],
        )
        assert task_id == "celery-uuid-1234"

    @pytest.mark.asyncio
    async def test_redis_queue_get_task_info_success(self):
        """SUCCESS Celery state maps to status='completed'."""
        queue = self._make_redis_queue()

        mock_ar = MagicMock()
        mock_ar.state = "SUCCESS"
        mock_ar.result = {"repository_id": "repo-1"}

        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult = MagicMock(return_value=mock_ar)

        with patch.dict("sys.modules", {"celery": MagicMock(), "celery.result": mock_celery_result}):
            info = await queue.get_task_info("task-id-xyz")

        assert info["status"] == "completed"
        assert info["mode"] == "redis"
        assert info["error"] is None

    @pytest.mark.asyncio
    async def test_redis_queue_get_task_info_failure(self):
        """FAILURE Celery state maps to status='failed' with error message."""
        queue = self._make_redis_queue()

        mock_ar = MagicMock()
        mock_ar.state = "FAILURE"
        mock_ar.result = RuntimeError("Disk full")

        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult = MagicMock(return_value=mock_ar)

        with patch.dict("sys.modules", {"celery": MagicMock(), "celery.result": mock_celery_result}):
            info = await queue.get_task_info("task-id-fail")

        assert info["status"] == "failed"
        assert "Disk full" in info["error"]

    @pytest.mark.asyncio
    async def test_redis_queue_get_task_info_running(self):
        """STARTED Celery state maps to status='running'."""
        queue = self._make_redis_queue()

        mock_ar = MagicMock()
        mock_ar.state = "STARTED"
        mock_ar.result = None

        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult = MagicMock(return_value=mock_ar)

        with patch.dict("sys.modules", {"celery": MagicMock(), "celery.result": mock_celery_result}):
            info = await queue.get_task_info("task-id-running")

        assert info["status"] == "running"

    @pytest.mark.asyncio
    async def test_redis_queue_get_task_info_pending(self):
        """PENDING Celery state maps to status='pending'."""
        queue = self._make_redis_queue()

        mock_ar = MagicMock()
        mock_ar.state = "PENDING"
        mock_ar.result = None

        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult = MagicMock(return_value=mock_ar)

        with patch.dict("sys.modules", {"celery": MagicMock(), "celery.result": mock_celery_result}):
            info = await queue.get_task_info("task-id-pending")

        assert info["status"] == "pending"

    @pytest.mark.asyncio
    async def test_redis_queue_get_task_info_retry(self):
        """RETRY Celery state maps to status='pending'."""
        queue = self._make_redis_queue()

        mock_ar = MagicMock()
        mock_ar.state = "RETRY"
        mock_ar.result = None

        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult = MagicMock(return_value=mock_ar)

        with patch.dict("sys.modules", {"celery": MagicMock(), "celery.result": mock_celery_result}):
            info = await queue.get_task_info("task-id-retry")

        assert info["status"] == "pending"

    @pytest.mark.asyncio
    async def test_redis_queue_list_tasks_returns_empty_list(self):
        """Redis mode returns empty list for list_tasks (no Flower)."""
        queue = self._make_redis_queue()
        result = await queue.list_tasks()
        assert result == []


# ─── Auto-selection & singleton ──────────────────────────────────────────────


class TestQueueAutoSelection:
    """Tests for get_task_queue() auto-detection and singleton behaviour."""

    def setup_method(self):
        from backend.worker.queue_adapter import reset_task_queue
        reset_task_queue()

    def teardown_method(self):
        from backend.worker.queue_adapter import reset_task_queue
        reset_task_queue()

    def test_reset_allows_reinitialisation(self, monkeypatch):
        """reset_task_queue() clears singleton so get_task_queue() rebuilds."""
        monkeypatch.setattr("backend.config.settings.settings.REDIS_URL", None)
        from backend.worker.queue_adapter import get_task_queue, reset_task_queue, LocalTaskQueue
        q1 = get_task_queue()
        reset_task_queue()
        q2 = get_task_queue()
        # Both should be LocalTaskQueue but different instances
        assert isinstance(q1, LocalTaskQueue)
        assert isinstance(q2, LocalTaskQueue)
        assert q1 is not q2

    def test_singleton_returns_same_instance_across_calls(self, monkeypatch):
        """get_task_queue() returns the same object on repeated calls."""
        monkeypatch.setattr("backend.config.settings.settings.REDIS_URL", None)
        from backend.worker.queue_adapter import get_task_queue
        q1 = get_task_queue()
        q2 = get_task_queue()
        assert q1 is q2
