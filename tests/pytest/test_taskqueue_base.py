from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.taskqueue.base import TaskQueue


class _FakeTaskQueue(TaskQueue):
    """Минимальная конкретная реализация — тестируем только lock(),
    остальные абстрактные методы не нужны для этих тестов."""

    def __init__(self, handle) -> None:
        self._handle = handle
        self.acquire_lock_calls: list[tuple[str, int]] = []

    async def acquire_lock(self, key: str, *, ttl_seconds: int = 60):
        self.acquire_lock_calls.append((key, ttl_seconds))
        return self._handle

    async def enqueue(self, *args, **kwargs):
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


def make_handle(acquired: bool = True) -> MagicMock:
    handle = MagicMock()
    handle.release = AsyncMock()
    return handle


@pytest.mark.asyncio
async def test_lock_acquired_yields_true_and_releases_on_exit() -> None:
    handle = make_handle()
    queue = _FakeTaskQueue(handle)

    async with queue.lock("subs:expire", ttl_seconds=30) as acquired:
        assert acquired is True
        handle.release.assert_not_awaited()

    assert queue.acquire_lock_calls == [("subs:expire", 30)]
    handle.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_busy_yields_false_and_does_not_call_release() -> None:
    queue = _FakeTaskQueue(None)

    async with queue.lock("subs:expire") as acquired:
        assert acquired is False


@pytest.mark.asyncio
async def test_lock_releases_even_if_body_raises() -> None:
    handle = make_handle()
    queue = _FakeTaskQueue(handle)

    async def _raise_inside_lock() -> None:
        async with queue.lock("subs:expire") as acquired:
            assert acquired is True
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await _raise_inside_lock()

    handle.release.assert_awaited_once()
