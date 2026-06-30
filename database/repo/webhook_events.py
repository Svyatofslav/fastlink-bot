from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import WebhookEventStatus
from database.models import WebhookEvent


class WebhookEventsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_event(
        self,
        *,
        provider: str,
        event_type: str,
        payload: dict[str, Any],
        external_id: str | None = None,
        idempotency_key: str | None = None,
        status: WebhookEventStatus = WebhookEventStatus.RECEIVED,
    ) -> WebhookEvent:
        if external_id is not None:
            stmt = select(WebhookEvent).where(
                WebhookEvent.provider == provider,
                WebhookEvent.external_id == external_id,
            )
            result = await self._session.execute(stmt)
            existing = result.scalars().first()
            if existing is not None:
                return existing

        event = WebhookEvent(
            provider=provider,
            event_type=event_type,
            external_id=external_id,
            idempotency_key=idempotency_key,
            status=status,
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def list_pending(
        self,
        *,
        provider: str | None = None,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        stmt = select(WebhookEvent).where(
            WebhookEvent.status == WebhookEventStatus.RECEIVED,
        )
        if provider is not None:
            stmt = stmt.where(WebhookEvent.provider == provider)

        stmt = stmt.order_by(WebhookEvent.created_at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_done(self, event_id: int) -> None:
        stmt = (
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(
                status=WebhookEventStatus.DONE,
                updated_at=datetime.now().astimezone(),
            )
        )
        await self._session.execute(stmt)

    async def mark_failed(self, event_id: int, error_message: str) -> None:
        now = datetime.now().astimezone()
        stmt = (
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(
                status=WebhookEventStatus.FAILED,
                error_message=error_message,
                last_retry_at=now,
                updated_at=now,
                retry_count=WebhookEvent.retry_count + 1,
            )
        )
        await self._session.execute(stmt)
