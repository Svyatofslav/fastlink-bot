from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import WebhookEventStatus
from database.repo import WebhookEventsRepo
from scheduler.jobs import process_webhook_events_with_session


@pytest.mark.asyncio
async def test_yookassa_webhook_missing_object_marks_event_failed(
    db_session: AsyncSession,
) -> None:
    """
    Если payload не содержит поля `object`, обработка события должна
    завершиться статусом FAILED, а воркер не должен падать.
    """
    repo = WebhookEventsRepo(session=db_session)

    event = await repo.create_event(
        provider="yookassa",
        event_type="payment.succeeded",
        external_id="test-payment-missing-object",
        idempotency_key=None,
        payload={
            "event": "payment.succeeded",
        },
        status=WebhookEventStatus.RECEIVED,
    )
    event_id = event.id
    await db_session.commit()

    await process_webhook_events_with_session(
        session=db_session,
        provider="yookassa",
        limit=10,
    )

    refreshed = await repo.get_by_id(event_id)
    assert refreshed is not None
    assert refreshed.status == WebhookEventStatus.FAILED


@pytest.mark.asyncio
async def test_yookassa_webhook_missing_payment_id_marks_event_failed(
    db_session: AsyncSession,
) -> None:
    """
    Если объект платежа не содержит поля `id`, событие должно стать FAILED.
    """
    repo = WebhookEventsRepo(session=db_session)

    payload = {
        "event": "payment.succeeded",
        "object": {
            "status": "succeeded",
            "amount": {"value": "100.00", "currency": "RUB"},
            "metadata": {"subscriptionid": 123},
        },
    }

    event = await repo.create_event(
        provider="yookassa",
        event_type="payment.succeeded",
        external_id="test-payment-missing-id",
        idempotency_key=None,
        payload=payload,
        status=WebhookEventStatus.RECEIVED,
    )
    event_id = event.id
    await db_session.commit()

    await process_webhook_events_with_session(
        session=db_session,
        provider="yookassa",
        limit=10,
    )

    refreshed = await repo.get_by_id(event_id)
    assert refreshed is not None
    assert refreshed.status == WebhookEventStatus.FAILED
