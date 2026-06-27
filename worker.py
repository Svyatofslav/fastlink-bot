from __future__ import annotations

import asyncio
import logging
import sys

import structlog

from config import settings
from scheduler.runner import run_worker


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


async def main() -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    logger.info("worker_starting", env=settings.app_env)
    await run_worker()


if __name__ == "__main__":
    asyncio.run(main())
