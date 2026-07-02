from __future__ import annotations

from typing import Any

import structlog

from infrastructure.taskqueue.arq_impl import ArqTaskQueue
from scheduler.jobs import process_webhook_events

logger = structlog.get_logger(__name__)

_WEBHOOK_LOCK_KEY = "webhook_events:process"
_WEBHOOK_LOCK_TTL_SECONDS = 30


async def run_process_webhook_events(
    ctx: dict[str, Any],
    provider: str = "test",
    limit: int = 100,
) -> None:
    """
    ARQ-обёртка над process_webhook_events.

    Вся бизнес-логика остаётся в scheduler.jobs — эту функцию можно
    покрыть тестами независимо от ARQ, просто мокнув process_webhook_events.
    """
    task_queue: ArqTaskQueue | None = ctx.get("task_queue")

    if task_queue is None:
        # Защитный фолбэк: если по какой-то причине task_queue не был
        # проинициализирован в on_startup — просто выполняем без лока,
        # но громко логируем, чтобы это не осталось незамеченным.
        logger.warning("webhook_tasks_lock_unavailable", provider=provider)
        await process_webhook_events(provider=provider, limit=limit)
        return

    async with task_queue.lock(
        _WEBHOOK_LOCK_KEY, ttl_seconds=_WEBHOOK_LOCK_TTL_SECONDS
    ) as acquired:
        if not acquired:
            logger.info("webhook_tasks_skip_locked", provider=provider)
            return
        await process_webhook_events(provider=provider, limit=limit)
