from __future__ import annotations

import logging
import sys

import structlog
from arq.worker import run_worker as arq_run_worker

from config import get_deploy_commit_short, settings
from tasks.worker_settings import WorkerSettings


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
    )


def main() -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    logger.info(
        "worker_starting",
        env=settings.app_env,
        deploy_commit_short=get_deploy_commit_short(),
    )
    # arq_run_worker — синхронная функция, она сама создаёт event loop
    # и подписывается на SIGINT/SIGTERM для graceful shutdown.
    # Оборачивать её в asyncio.run/run_in_executor нельзя — это ломает
    # создание event loop внутри arq.Worker.
    arq_run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
