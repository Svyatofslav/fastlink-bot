from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tasks.worker_settings import shutdown, startup


@pytest.mark.asyncio
async def test_startup_populates_ctx_with_task_queue_and_bot() -> None:
    fake_queue = AsyncMock()
    fake_bot = MagicMock()

    with (
        patch(
            "tasks.worker_settings.ArqTaskQueue.create",
            new=AsyncMock(return_value=fake_queue),
        ) as create_mock,
        patch("tasks.worker_settings.Bot", return_value=fake_bot) as bot_cls,
    ):
        ctx: dict = {}
        await startup(ctx)

    create_mock.assert_awaited_once()
    bot_cls.assert_called_once()
    assert ctx["task_queue"] is fake_queue
    assert ctx["bot"] is fake_bot


@pytest.mark.asyncio
async def test_shutdown_closes_task_queue_and_bot_session() -> None:
    fake_queue = AsyncMock()
    fake_bot = MagicMock()
    fake_bot.session.close = AsyncMock()

    ctx = {"task_queue": fake_queue, "bot": fake_bot}
    await shutdown(ctx)

    fake_queue.close.assert_awaited_once()
    fake_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_handles_missing_task_queue_and_bot() -> None:
    ctx: dict = {}

    await shutdown(ctx)  # не должно бросить исключение


@pytest.mark.asyncio
async def test_shutdown_handles_none_task_queue_and_bot() -> None:
    ctx = {"task_queue": None, "bot": None}

    await shutdown(ctx)  # не должно бросить исключение
