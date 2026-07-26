# database/repo/webhook_events.py

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from database.enums import WebhookEventStatus
from database.models import WebhookEvent
from database.repo.base import BaseRepo


class WebhookEventsRepo(BaseRepo[WebhookEvent]):
    model = WebhookEvent

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
        """
        Идемпотентно по (provider, external_id): платёжный провайдер может
        продублировать вебхук (retry при таймауте на нашей стороне), а два
        конкурентных запроса/воркера могут обрабатывать один и тот же
        входящий webhook параллельно. Pre-check SELECT сам по себе не
        защищает от гонки между двумя параллельными вызовами — оборачиваем
        INSERT в SAVEPOINT и ловим IntegrityError по
        uq_webhook_events_provider_external_id, возвращая уже
        существующую запись вместо падения наружу.
        """
        if external_id is not None:
            stmt = select(WebhookEvent).where(
                WebhookEvent.provider == provider,
                WebhookEvent.external_id == external_id,
            )
            result = await self.session.execute(stmt)
            existing = result.scalars().first()
            if existing is not None:
                return existing

        try:
            async with self.session.begin_nested():
                event = await self.create(
                    provider=provider,
                    event_type=event_type,
                    external_id=external_id,
                    idempotency_key=idempotency_key,
                    status=status,
                    payload=payload,
                )
        except IntegrityError:
            if external_id is None:
                raise
            stmt = select(WebhookEvent).where(
                WebhookEvent.provider == provider,
                WebhookEvent.external_id == external_id,
            )
            result = await self.session.execute(stmt)
            existing = result.scalars().first()
            if existing is None:
                raise
            return existing

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

        stmt = (
            stmt.order_by(WebhookEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
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
        await self.session.execute(stmt)

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
        await self.session.execute(stmt)
