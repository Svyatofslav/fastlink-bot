from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

import structlog

from config import get_deploy_commit_short
from scheduler.jobs import process_webhook_events

logger = structlog.get_logger(__name__)


class WorkerRunner:
    def __init__(self, interval_seconds: int = 5) -> None:
        self._stop_event = asyncio.Event()
        self._interval_seconds = interval_seconds

    def _setup_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop_event.set)

    async def _run_loop(self) -> None:
        logger.info(
            "worker_runner_started",
            deploy_commit_short=get_deploy_commit_short(),
        )
        try:
            while not self._stop_event.is_set():
                await process_webhook_events(provider="test", limit=100)
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._interval_seconds
                    )
                except asyncio.TimeoutError:
                    # просто продолжаем цикл
                    pass
        finally:
            logger.info("worker_runner_stopped")

    async def run(self) -> None:
        self._setup_signals()
        await self._run_loop()


async def run_worker() -> None:
    runner = WorkerRunner(interval_seconds=5)
    await runner.run()
