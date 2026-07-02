from __future__ import annotations

from typing import Any

import structlog
from arq import cron
from arq.connections import RedisSettings

from config import get_deploy_commit_short
from infrastructure.taskqueue.arq_impl import ArqTaskQueue, build_redis_settings
from tasks.webhook_tasks import run_process_webhook_events

logger = structlog.get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["task_queue"] = await ArqTaskQueue.create()
    logger.info(
        "arq_worker_startup",
        deploy_commit_short=get_deploy_commit_short(),
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    task_queue: ArqTaskQueue | None = ctx.get("task_queue")
    if task_queue is not None:
        await task_queue.close()
    logger.info("arq_worker_shutdown")


class WorkerSettings:
    redis_settings: RedisSettings = build_redis_settings()
    functions = [run_process_webhook_events]
    cron_jobs = [
        cron(
            run_process_webhook_events,
            second=set(range(0, 60, 5)),  # каждые 5 секунд — как в старом WorkerRunner
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 30
