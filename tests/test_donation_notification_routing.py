from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from database.enums import PaymentProvider, PaymentStatus
from database.repo.payments import PaymentRepo
from database.repo.users import UserRepo
from scheduler.jobs import _handle_payment_succeeded

REALISTIC_DONATION_METADATA_SNAPSHOT = {
    "amount_value": "100.00",
    "amount_currency": "RUB",
    "paid": True,
    "description": "FastLink payment #1",
    "metadata": {"type": "donation", "user_id": "1"},
}


@pytest.mark.asyncio
async def test_donation_webhook_routes_to_donation_notify(db_session):
    users = UserRepo(db_session)
    user = await users.create(
        telegram_id=555555,
        username="donor",
        first_name="Test",
        last_name="Donor",
        language_code="ru",
    )

    payments = PaymentRepo(db_session)
    payment = await payments.create(
        user_id=user.id,
        subscription_id=None,
        provider=PaymentProvider.YOOKASSA,
        provider_payment_id="yk-donation-123",
        amount=10000,
        currency="RUB",
        status=PaymentStatus.PENDING,
        idempotence_key="donation-idem-key",
        metadata_snapshot={
            "type": "donation",
            "user": {"id": user.id},
            "amount": 10000,
        },
        paid_at=None,
        refundable=False,
        refunded_amount=0,
    )
    await db_session.commit()

    webhook_payload = {
        "object": {
            "id": "yk-donation-123",
            "amount": {"value": "100.00", "currency": "RUB"},
            "paid": True,
            "description": f"FastLink payment #{payment.id}",
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {"type": "donation", "user_id": str(user.id)},
        }
    }

    fake_event = type("FakeEvent", (), {"id": 1})()

    with (
        patch(
            "scheduler.jobs.notify_donation_succeeded", new=AsyncMock()
        ) as donation_notify,
        patch(
            "scheduler.jobs._notify_payment_succeeded", new=AsyncMock()
        ) as payment_notify,
    ):
        await _handle_payment_succeeded(
            db_session, fake_event, webhook_payload, bot=None
        )

    donation_notify.assert_awaited_once()
    payment_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_regular_payment_webhook_routes_to_payment_notify(db_session):
    users = UserRepo(db_session)
    user = await users.create(
        telegram_id=666666,
        username="buyer",
        first_name="Test",
        last_name="Buyer",
        language_code="ru",
    )

    payments = PaymentRepo(db_session)
    payment = await payments.create(
        user_id=user.id,
        subscription_id=None,
        provider=PaymentProvider.YOOKASSA,
        provider_payment_id="yk-sub-456",
        amount=29900,
        currency="RUB",
        status=PaymentStatus.PENDING,
        idempotence_key="sub-idem-key",
        metadata_snapshot={
            "user": {"id": user.id},
            "server": {"id": 1},
            "tariff": {"id": 1},
            "subscription": {"marzban_username": "fl_1_123"},
        },
        paid_at=None,
        refundable=False,
        refunded_amount=0,
    )
    await db_session.commit()

    webhook_payload = {
        "object": {
            "id": "yk-sub-456",
            "amount": {"value": "299.00", "currency": "RUB"},
            "paid": True,
            "description": f"FastLink payment #{payment.id}",
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {
                "tariff_id": "1",
                "server_id": "1",
                "marzban_username": "fl_1_123",
            },
        }
    }

    fake_event = type("FakeEvent", (), {"id": 2})()

    with (
        patch(
            "scheduler.jobs.notify_donation_succeeded", new=AsyncMock()
        ) as donation_notify,
        patch(
            "scheduler.jobs._notify_payment_succeeded", new=AsyncMock()
        ) as payment_notify,
    ):
        await _handle_payment_succeeded(
            db_session, fake_event, webhook_payload, bot=None
        )

    payment_notify.assert_awaited_once()
    donation_notify.assert_not_awaited()
