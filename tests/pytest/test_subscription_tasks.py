from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tasks.subscription_tasks import (
    _EXPIRE_LOCK_KEY,
    _LOCK_TTL_SECONDS,
    _REMINDER_1D_LOCK_KEY,
    _REMINDER_3D_LOCK_KEY,
    run_expire_overdue_subscriptions,
    run_send_expiration_reminders_1d,
    run_send_expiration_reminders_3d,
)


def _make_ctx_with_lock(acquired: bool) -> tuple[dict, MagicMock]:
    task_queue = MagicMock()
    lock_cm = MagicMock()
    lock_cm.__aenter__ = AsyncMock(return_value=acquired)
    lock_cm.__aexit__ = AsyncMock(return_value=False)
    task_queue.lock = MagicMock(return_value=lock_cm)
    return {"task_queue": task_queue}, task_queue


CASES = [
    (
        run_expire_overdue_subscriptions,
        "tasks.subscription_tasks.expire_overdue_subscriptions",
        _EXPIRE_LOCK_KEY,
    ),
    (
        run_send_expiration_reminders_3d,
        "tasks.subscription_tasks.send_expiration_reminders_3d",
        _REMINDER_3D_LOCK_KEY,
    ),
    (
        run_send_expiration_reminders_1d,
        "tasks.subscription_tasks.send_expiration_reminders_1d",
        _REMINDER_1D_LOCK_KEY,
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("run_func", "patch_target", "lock_key"), CASES)
async def test_runs_job_when_lock_acquired(
    run_func, patch_target, lock_key, monkeypatch
) -> None:
    mocked = AsyncMock()
    monkeypatch.setattr(patch_target, mocked)

    ctx, task_queue = _make_ctx_with_lock(acquired=True)
    await run_func(ctx)

    mocked.assert_awaited_once_with()
    task_queue.lock.assert_called_once_with(lock_key, ttl_seconds=_LOCK_TTL_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize(("run_func", "patch_target", "lock_key"), CASES)
async def test_skips_job_when_lock_busy(
    run_func, patch_target, lock_key, monkeypatch
) -> None:
    mocked = AsyncMock()
    monkeypatch.setattr(patch_target, mocked)

    ctx, task_queue = _make_ctx_with_lock(acquired=False)
    await run_func(ctx)

    mocked.assert_not_awaited()
    task_queue.lock.assert_called_once_with(lock_key, ttl_seconds=_LOCK_TTL_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize(("run_func", "patch_target", "lock_key"), CASES)
async def test_runs_without_lock_if_task_queue_missing(
    run_func, patch_target, lock_key, monkeypatch
) -> None:
    mocked = AsyncMock()
    monkeypatch.setattr(patch_target, mocked)

    await run_func({})

    mocked.assert_awaited_once_with()
