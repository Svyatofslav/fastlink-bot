from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from database.enums import (
    NotificationDeliveryStatus,
    NotificationType,
    PaymentProvider,
    PaymentStatus,
)
from database.models import NotificationLog, User
from database.repo.payments import PaymentRepo
from domain.donation_metadata import build_donation_metadata
from scheduler.jobs import _handle_payment_succeeded
from services.payment import PaymentService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_user(db_session: AsyncSession, telegram_id: int) -> User:
    user = User(
        telegram_id=telegram_id,
        username="donor3",
        first_name="Test",
        last_name="Donor3",
        language_code="ru",
        is_banned=False,
        is_active=True,
        last_active_at=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_donation_webhook_persists_real_notification(
    db_session: AsyncSession,
) -> None:
    """
    Без мокирования notify_donation_succeeded: проверяем, что после реального
    webhook payment.succeeded в NotificationLog появляется ровно одна запись
    DONATION_SUCCEEDED, а повторный webhook не создаёт вторую (дедуп).
    """
    user = await _make_user(db_session, telegram_id=900_000_001)
    payment_service = PaymentService(db_session)
    metadata_snapshot = build_donation_metadata(user=user, amount=20000, currency="RUB")

    payment = await payment_service.create_payment(
        user_id=user.id,
        amount=20000,
        currency="RUB",
        provider=PaymentProvider.YOOKASSA,
        subscription_id=None,
        idempotency_key="donation-webhook-1",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()
    await db_session.refresh(payment)

    await payment_service.attach_provider_payment_id(
        payment_id=payment.id, provider_payment_id="yk-donation-webhook-1"
    )
    await db_session.commit()

    webhook_payload = {
        "object": {
            "id": "yk-donation-webhook-1",
            "amount": {"value": "200.00", "currency": "RUB"},
            "paid": True,
            "description": f"FastLink payment #{payment.id}",
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {"type": "donation", "user_id": str(user.id)},
        }
    }
    fake_event = type("FakeEvent", (), {"id": 1})()
    fake_bot = AsyncMock()

    await _handle_payment_succeeded(
        db_session, fake_event, webhook_payload, bot=fake_bot
    )
    await db_session.commit()

    fake_bot.send_message.assert_awaited_once()

    result = await db_session.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == user.id,
            NotificationLog.type == NotificationType.DONATION_SUCCEEDED,
        )
    )
    logs = list(result.scalars().all())
    assert len(logs) == 1
    assert logs[0].delivery_status == NotificationDeliveryStatus.SENT

    fake_bot.send_message.reset_mock()
    await _handle_payment_succeeded(
        db_session, fake_event, webhook_payload, bot=fake_bot
    )
    await db_session.commit()

    fake_bot.send_message.assert_not_awaited()

    result_again = await db_session.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == user.id,
            NotificationLog.type == NotificationType.DONATION_SUCCEEDED,
        )
    )
    assert len(list(result_again.scalars().all())) == 1


@pytest.mark.asyncio
async def test_donation_cancel_pending_and_retry_after_cancellation(
    db_session: AsyncSession,
) -> None:
    """
    Пользователь отменяет донат в статусе PENDING, затем делает новую попытку
    с новым idempotency_key — новая попытка должна пройти без конфликтов.
    """
    user = await _make_user(db_session, telegram_id=900_000_002)
    payment_service = PaymentService(db_session)
    payments_repo = PaymentRepo(db_session)
    metadata_snapshot = build_donation_metadata(user=user, amount=30000, currency="RUB")

    first_payment = await payment_service.create_payment(
        user_id=user.id,
        amount=30000,
        currency="RUB",
        provider=PaymentProvider.YOOKASSA,
        subscription_id=None,
        idempotency_key="donation-cancel-1",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()

    canceled = await payment_service.cancel_pending_payment(payment_id=first_payment.id)
    await db_session.commit()
    assert canceled.status == PaymentStatus.CANCELED
    assert canceled.refundable is False

    canceled_again = await payment_service.cancel_pending_payment(
        payment_id=first_payment.id
    )
    assert canceled_again.status == PaymentStatus.CANCELED

    second_payment = await payment_service.create_payment(
        user_id=user.id,
        amount=30000,
        currency="RUB",
        provider=PaymentProvider.YOOKASSA,
        subscription_id=None,
        idempotency_key="donation-cancel-2",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()

    assert second_payment.status == PaymentStatus.PENDING
    assert second_payment.id != first_payment.id

    stored_first = await payments_repo.get_by_id(first_payment.id)
    assert stored_first.status == PaymentStatus.CANCELED
