from __future__ import annotations

from typing import Any

import structlog
from aiohttp import web

from database.session import get_async_session_factory
from database.repo.webhook_events import WebhookEventsRepo


logger = structlog.get_logger(__name__)


async def test_webhook(request: web.Request) -> web.Response:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        logger.warning("test_webhook_invalid_json")
        return web.Response(status=400, text="invalid json")

    factory = get_async_session_factory()
    async with factory() as session:  # type: AsyncSession
        repo = WebhookEventsRepo(session=session)
        try:
            await repo.create_event(
                provider="test",
                event_type="test.event",
                payload=payload,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("test_webhook_processing_error")
            return web.Response(status=500, text="error")

    return web.Response(status=200, text="ok")
