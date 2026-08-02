from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from scheduler.jobs import process_webhook_events

if TYPE_CHECKING:
    from infrastructure.taskqueue.arq_impl import ArqTaskQueue

logger = structlog.get_logger(__name__)

_WEBHOOK_LOCK_KEY = "webhook_events:process"
_WEBHOOK_LOCK_TTL_SECONDS = 30


async def run_process_webhook_events(
    ctx: dict[str, Any], provider: str = "test", limit: int = 100
) -> None:
    task_queue: ArqTaskQueue | None = ctx.get("task_queue")
    bot = ctx.get("bot")
    if task_queue is None:
        logger.warning("webhook_tasks_lock_unavailable", provider=provider)
        await process_webhook_events(provider=provider, limit=limit, bot=bot)
        return
    async with task_queue.lock(
        _WEBHOOK_LOCK_KEY, ttl_seconds=_WEBHOOK_LOCK_TTL_SECONDS
    ) as acquired:
        if not acquired:
            logger.info("webhook_tasks_skip_locked", provider=provider)
            return
        await process_webhook_events(provider=provider, limit=limit, bot=bot)
