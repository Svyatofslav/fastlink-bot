from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq.connections import RedisSettings

from infrastructure.taskqueue.arq_impl import (
    _LOCK_KEY_PREFIX,
    _RELEASE_LOCK_SCRIPT,
    ArqTaskQueue,
    _ArqLockHandle,
)
from infrastructure.taskqueue.contracts import (
    TaskEnqueueError,
    TaskQueueConnectionError,
)


def make_redis_mock() -> MagicMock:
    redis = MagicMock()
    redis.eval = AsyncMock()
    redis.enqueue_job = AsyncMock()
    redis.set = AsyncMock()
    redis.close = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# _ArqLockHandle.release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_handle_release_calls_eval_and_marks_not_acquired() -> None:
    redis = make_redis_mock()
    handle = _ArqLockHandle(_redis=redis, _key="taskqueue:lock:x", _token="tok-1")

    await handle.release()

    redis.eval.assert_awaited_once_with(
        _RELEASE_LOCK_SCRIPT, 1, "taskqueue:lock:x", "tok-1"
    )
    assert handle.acquired is False


@pytest.mark.asyncio
async def test_lock_handle_release_is_noop_when_not_acquired() -> None:
    redis = make_redis_mock()
    handle = _ArqLockHandle(
        _redis=redis, _key="taskqueue:lock:x", _token="tok-1", _acquired=False
    )

    await handle.release()

    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_lock_handle_release_marks_not_acquired_even_if_eval_fails() -> None:
    redis = make_redis_mock()
    redis.eval = AsyncMock(side_effect=Exception("redis down"))
    handle = _ArqLockHandle(_redis=redis, _key="taskqueue:lock:x", _token="tok-1")

    with pytest.raises(Exception, match="redis down"):
        await handle.release()

    assert handle.acquired is False


# ---------------------------------------------------------------------------
# ArqTaskQueue.create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_success_returns_task_queue() -> None:
    redis = make_redis_mock()
    settings_obj = RedisSettings(host="localhost", port=6379)

    with patch(
        "infrastructure.taskqueue.arq_impl.create_pool",
        new=AsyncMock(return_value=redis),
    ) as create_pool_mock:
        queue = await ArqTaskQueue.create(settings_obj)

    assert isinstance(queue, ArqTaskQueue)
    create_pool_mock.assert_awaited_once_with(settings_obj)


@pytest.mark.asyncio
async def test_create_uses_build_redis_settings_when_none_passed() -> None:
    redis = make_redis_mock()
    fallback_settings = RedisSettings(host="fallback", port=6380)

    with (
        patch(
            "infrastructure.taskqueue.arq_impl.create_pool",
            new=AsyncMock(return_value=redis),
        ) as create_pool_mock,
        patch(
            "infrastructure.taskqueue.arq_impl.build_redis_settings",
            return_value=fallback_settings,
        ),
    ):
        await ArqTaskQueue.create(None)

    create_pool_mock.assert_awaited_once_with(fallback_settings)


@pytest.mark.asyncio
async def test_create_connection_failure_raises_task_queue_connection_error() -> None:
    settings_obj = RedisSettings(host="localhost", port=6379)

    with (
        patch(
            "infrastructure.taskqueue.arq_impl.create_pool",
            new=AsyncMock(side_effect=OSError("connection refused")),
        ),
        pytest.raises(TaskQueueConnectionError),
    ):
        await ArqTaskQueue.create(settings_obj)


# ---------------------------------------------------------------------------
# ArqTaskQueue.enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_success_returns_job_id() -> None:
    redis = make_redis_mock()
    job = MagicMock(job_id="job-123")
    redis.enqueue_job = AsyncMock(return_value=job)
    queue = ArqTaskQueue(redis)

    result = await queue.enqueue(
        "some_task", 1, 2, job_id="idem-1", defer_by_seconds=10
    )

    assert result == "job-123"
    redis.enqueue_job.assert_awaited_once_with(
        "some_task", 1, 2, _job_id="idem-1", _defer_by=10
    )


@pytest.mark.asyncio
async def test_enqueue_deduped_returns_none() -> None:
    redis = make_redis_mock()
    redis.enqueue_job = AsyncMock(return_value=None)
    queue = ArqTaskQueue(redis)

    result = await queue.enqueue("some_task", job_id="idem-1")

    assert result is None


@pytest.mark.asyncio
async def test_enqueue_failure_raises_task_enqueue_error() -> None:
    redis = make_redis_mock()
    redis.enqueue_job = AsyncMock(side_effect=OSError("boom"))
    queue = ArqTaskQueue(redis)

    with pytest.raises(TaskEnqueueError):
        await queue.enqueue("some_task")


# ---------------------------------------------------------------------------
# ArqTaskQueue.acquire_lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_lock_success_returns_handle() -> None:
    redis = make_redis_mock()
    redis.set = AsyncMock(return_value=True)
    queue = ArqTaskQueue(redis)

    handle = await queue.acquire_lock("subs:expire", ttl_seconds=30)

    assert handle is not None
    assert handle.acquired is True
    call_args = redis.set.await_args
    assert call_args.args[0] == f"{_LOCK_KEY_PREFIX}subs:expire"
    assert call_args.kwargs["nx"] is True
    assert call_args.kwargs["ex"] == 30


@pytest.mark.asyncio
async def test_acquire_lock_busy_returns_none() -> None:
    redis = make_redis_mock()
    redis.set = AsyncMock(return_value=None)
    queue = ArqTaskQueue(redis)

    handle = await queue.acquire_lock("subs:expire")

    assert handle is None


# ---------------------------------------------------------------------------
# ArqTaskQueue.close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_closes_redis_connection() -> None:
    redis = make_redis_mock()
    queue = ArqTaskQueue(redis)

    await queue.close()

    redis.close.assert_awaited_once()
