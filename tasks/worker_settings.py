from __future__ import annotations

from typing import Any

import structlog
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from arq import cron
from arq.connections import RedisSettings

from config import get_deploy_commit_short, settings
from infrastructure.taskqueue.arq_impl import ArqTaskQueue, build_redis_settings
from tasks.webhook_tasks import run_process_webhook_events
from tasks.subscription_tasks import (
    run_expire_overdue_subscriptions,
    run_send_expiration_reminders_1d,
    run_send_expiration_reminders_3d,
)

logger = structlog.get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["task_queue"] = await ArqTaskQueue.create()
    ctx["bot"] = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=settings.bot_parse_mode),
    )
    logger.info(
        "arq_worker_startup",
        deploy_commit_short=get_deploy_commit_short(),
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    task_queue: ArqTaskQueue | None = ctx.get("task_queue")
    if task_queue is not None:
        await task_queue.close()
    bot: Bot | None = ctx.get("bot")
    if bot is not None:
        await bot.session.close()
    logger.info("arq_worker_shutdown")


class WorkerSettings:
    redis_settings: RedisSettings = build_redis_settings()
    functions = [
        run_process_webhook_events,
        run_expire_overdue_subscriptions,
        run_send_expiration_reminders_3d,
        run_send_expiration_reminders_1d,
    ]
    cron_jobs = [
        cron(
            run_process_webhook_events,
            second=set(range(0, 60, 5)),
        ),
        cron(
            run_expire_overdue_subscriptions,
            minute=set(range(0, 60, 15)),
        ),
        cron(
            run_send_expiration_reminders_3d,
            hour={9},
            minute={0},
        ),
        cron(
            run_send_expiration_reminders_1d,
            hour={9},
            minute={5},
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 30
