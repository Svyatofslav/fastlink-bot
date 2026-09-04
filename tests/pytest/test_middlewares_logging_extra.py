from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from middlewares.logging import LoggingMiddleware


@pytest.mark.asyncio
async def test_logging_middleware_reraises_handler_exception() -> None:
    middleware = LoggingMiddleware()
    event = MagicMock()
    event.text = "hi"

    async def failing_handler(_event, _data):
        raise ValueError("handler exploded")

    with pytest.raises(ValueError, match="handler exploded"):
        await middleware(failing_handler, event, {})


@pytest.mark.asyncio
async def test_logging_middleware_returns_handler_result_on_success() -> None:
    middleware = LoggingMiddleware()
    event = MagicMock()
    event.text = "hi"
    handler = AsyncMock(return_value="ok")

    result = await middleware(handler, event, {})

    assert result == "ok"
