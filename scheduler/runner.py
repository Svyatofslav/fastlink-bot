from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

import structlog

logger = structlog.get_logger(__name__)


class WorkerRunner:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()

    def _setup_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop_event.set)

    async def run(self) -> None:
        self._setup_signals()
        logger.info("worker_runner_started")
        await self._stop_event.wait()
        logger.info("worker_runner_stopped")


async def run_worker() -> None:
    runner = WorkerRunner()
    await runner.run()
