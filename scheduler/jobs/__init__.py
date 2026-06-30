from __future__ import annotations

from typing import Any

import structlog

from database.session import get_async_session_factory
from database.repo.webhook_events import WebhookEventsRepo

logger = structlog.get_logger(__name__)


async def process_webhook_events(provider: str = "test", limit: int = 100) -> None:
    factory = get_async_session_factory()
    async with factory() as session:
        repo = WebhookEventsRepo(session=session)
        try:
            events = await repo.list_pending(provider=provider, limit=limit)
            if not events:
                return

            logger.info(
                "webhook_events_processing_started",
                provider=provider,
                count=len(events),
            )

            for event in events:
                try:
                    await handle_single_event(repo, event)
                    await repo.mark_done(event.id)
                except Exception as exc:
                    logger.exception(
                        "webhook_event_processing_failed",
                        event_id=event.id,
                        provider=event.provider,
                        exc_info=exc,
                    )
                    await repo.mark_failed(event.id, error_message=str(exc))

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("webhook_events_batch_failed")


async def handle_single_event(repo: WebhookEventsRepo, event: Any) -> None:
    logger.info(
        "webhook_event_processed",
        event_id=event.id,
        provider=event.provider,
        event_type=event.event_type,
    )
    # Здесь позже появится реальная логика (YooKassa, Telegram и т.п.),
    # сейчас это скелет, который просто логирует факт обработки.
