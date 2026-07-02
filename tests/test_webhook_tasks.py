from unittest.mock import AsyncMock, MagicMock

import pytest

from tasks.webhook_tasks import run_process_webhook_events


def _make_ctx_with_lock(acquired: bool) -> dict:
    task_queue = MagicMock()
    lock_cm = MagicMock()
    lock_cm.__aenter__ = AsyncMock(return_value=acquired)
    lock_cm.__aexit__ = AsyncMock(return_value=False)
    task_queue.lock = MagicMock(return_value=lock_cm)
    return {"task_queue": task_queue}


@pytest.mark.asyncio
async def test_runs_job_when_lock_acquired(monkeypatch):
    mocked = AsyncMock()
    monkeypatch.setattr("tasks.webhook_tasks.process_webhook_events", mocked)

    ctx = _make_ctx_with_lock(acquired=True)
    await run_process_webhook_events(ctx, provider="yookassa", limit=50)

    mocked.assert_awaited_once_with(provider="yookassa", limit=50)


@pytest.mark.asyncio
async def test_skips_job_when_lock_busy(monkeypatch):
    mocked = AsyncMock()
    monkeypatch.setattr("tasks.webhook_tasks.process_webhook_events", mocked)

    ctx = _make_ctx_with_lock(acquired=False)
    await run_process_webhook_events(ctx, provider="test", limit=100)

    mocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_runs_without_lock_if_task_queue_missing(monkeypatch):
    mocked = AsyncMock()
    monkeypatch.setattr("tasks.webhook_tasks.process_webhook_events", mocked)

    await run_process_webhook_events({}, provider="test", limit=100)

    mocked.assert_awaited_once_with(provider="test", limit=100)
