from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from scheduler.jobs import (
    expire_overdue_subscriptions,
    send_expiration_reminders_1d,
    send_expiration_reminders_3d,
)

if TYPE_CHECKING:
    from infrastructure.taskqueue.arq_impl import ArqTaskQueue

logger = structlog.get_logger(__name__)

_EXPIRE_LOCK_KEY = "subscriptions:expire_overdue"
_REMINDER_3D_LOCK_KEY = "subscriptions:reminder_3d"
_REMINDER_1D_LOCK_KEY = "subscriptions:reminder_1d"
_LOCK_TTL_SECONDS = 60


async def run_expire_overdue_subscriptions(ctx: dict[str, Any]) -> None:
    task_queue: ArqTaskQueue | None = ctx.get("task_queue")
    if task_queue is None:
        logger.warning("expire_overdue_lock_unavailable")
        await expire_overdue_subscriptions()
        return
    async with task_queue.lock(
        _EXPIRE_LOCK_KEY, ttl_seconds=_LOCK_TTL_SECONDS
    ) as acquired:
        if not acquired:
            logger.info("expire_overdue_skip_locked")
            return
        await expire_overdue_subscriptions()


async def run_send_expiration_reminders_3d(ctx: dict[str, Any]) -> None:
    task_queue: ArqTaskQueue | None = ctx.get("task_queue")
    if task_queue is None:
        logger.warning("reminder_3d_lock_unavailable")
        await send_expiration_reminders_3d()
        return
    async with task_queue.lock(
        _REMINDER_3D_LOCK_KEY, ttl_seconds=_LOCK_TTL_SECONDS
    ) as acquired:
        if not acquired:
            logger.info("reminder_3d_skip_locked")
            return
        await send_expiration_reminders_3d()


async def run_send_expiration_reminders_1d(ctx: dict[str, Any]) -> None:
    task_queue: ArqTaskQueue | None = ctx.get("task_queue")
    if task_queue is None:
        logger.warning("reminder_1d_lock_unavailable")
        await send_expiration_reminders_1d()
        return
    async with task_queue.lock(
        _REMINDER_1D_LOCK_KEY, ttl_seconds=_LOCK_TTL_SECONDS
    ) as acquired:
        if not acquired:
            logger.info("reminder_1d_skip_locked")
            return
        await send_expiration_reminders_1d()
