from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import WebhookEventStatus
from database.models import WebhookEvent
from database.repo.webhook_events import WebhookEventsRepo


@pytest.mark.asyncio
async def test_create_event_and_idempotency(db_session: AsyncSession) -> None:
    repo = WebhookEventsRepo(session=db_session)

    event1 = await repo.create_event(
        provider="test",
        event_type="test.event",
        payload={"foo": "bar"},
        external_id="ext-1",
    )
    await db_session.commit()

    # Явно читаем из БД — независимо от состояния объекта в памяти
    await db_session.refresh(event1)
    assert event1.status == WebhookEventStatus.RECEIVED, (
        f"Expected RECEIVED right after creation, got {event1.status}"
    )

    event1_id = event1.id  # сохраняем до второго create_event

    event2 = await repo.create_event(
        provider="test",
        event_type="test.event",
        payload={"foo": "baz"},
        external_id="ext-1",
    )
    await db_session.commit()

    assert event1_id == event2.id, (
        "Idempotency: same external_id must return same record"
    )
    assert event2.provider == "test"
    assert event2.external_id == "ext-1"


@pytest.mark.asyncio
async def test_mark_done_and_failed(db_session: AsyncSession) -> None:
    repo = WebhookEventsRepo(session=db_session)

    event = await repo.create_event(
        provider="test",
        event_type="test.event",
        payload={"foo": "bar"},
        external_id="ext-2",
    )
    await db_session.commit()

    await repo.mark_done(event.id)
    await db_session.commit()

    result = await db_session.execute(
        select(WebhookEvent).where(WebhookEvent.id == event.id)
    )
    loaded = result.scalars().one()
    assert loaded.status == WebhookEventStatus.DONE

    await repo.mark_failed(event.id, error_message="oops")
    await db_session.commit()

    result = await db_session.execute(
        select(WebhookEvent).where(WebhookEvent.id == event.id)
    )
    loaded = result.scalars().one()
    assert loaded.status == WebhookEventStatus.FAILED
    assert loaded.error_message == "oops"
    assert loaded.retry_count >= 1
