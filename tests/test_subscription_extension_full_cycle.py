from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from database.enums import DisabledReason, PaymentProvider, SubscriptionStatus
from database.models import Server, Subscription, Tariff, User
from domain.purchase_metadata import build_purchase_metadata
from scheduler.jobs import _handle_payment_succeeded
from services.payment import PaymentService
from states.purchase import DATA_EXTEND_SUBSCRIPTION_ID, DATA_IS_EXTEND

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_active_subscription(db_session: AsyncSession, *, days_left: int):
    user = User(telegram_id=800_000_001)
    server = Server(name="ext-server", inbound_tag="ext-inbound")
    tariff = Tariff(
        server_id=None,
        name="Ext tariff",
        duration_days=30,
        data_limit_bytes=5_000_000,
        price_amount=29900,
        price_currency="RUB",
    )
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    now = datetime.now(UTC)
    subscription = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="ext-user",
        status=SubscriptionStatus.ACTIVE,
        starts_at=now - timedelta(days=30 - days_left),
        expires_at=now + timedelta(days=days_left),
        data_limit_bytes=5_000_000,
        data_used_bytes=4_500_000,
        auto_renew=False,
        subscription_url="https://example.com/sub/ext-user",
        disabled_reason=None,
    )
    db_session.add(subscription)
    await db_session.commit()
    return user, server, tariff, subscription


async def _fake_set_enabled(
    self,
    *,
    subscription_id: int,
    enabled: bool,
    disabled_reason: DisabledReason | None,
) -> Subscription:
    session: AsyncSession = self._session
    result = await session.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    sub: Subscription = result.scalars().one()
    if enabled:
        sub.status = SubscriptionStatus.ACTIVE
        sub.disabled_reason = None
    else:
        sub.status = SubscriptionStatus.DISABLED
        sub.disabled_reason = disabled_reason
    session.add(sub)
    await session.flush()
    await session.refresh(sub)
    return sub


def _build_extension_metadata_snapshot(user, server, tariff, subscription):
    """
    Строит metadata_snapshot ровно так, как это делает production-хендлер
    on_subscription_extend после патча — через build_purchase_metadata с
    флагами is_extend/extend_subscription_id, а не произвольный плоский словарь.
    """
    return build_purchase_metadata(
        user=user,
        server=server,
        tariff=tariff,
        fsm_data={
            DATA_IS_EXTEND: True,
            DATA_EXTEND_SUBSCRIPTION_ID: subscription.id,
        },
    )


@pytest.mark.asyncio
async def test_extension_payment_extends_expires_at_and_resets_traffic(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(
        "services.marzban_subscription.SubscriptionMarzbanService.set_enabled",
        _fake_set_enabled,
    )

    user, server, tariff, subscription = await _make_active_subscription(
        db_session, days_left=5
    )
    old_expires_at = subscription.expires_at

    payment_service = PaymentService(db_session)
    metadata_snapshot = _build_extension_metadata_snapshot(
        user, server, tariff, subscription
    )
    payment = await payment_service.create_payment(
        user_id=user.id,
        amount=tariff.price_amount,
        currency=tariff.price_currency,
        provider=PaymentProvider.YOOKASSA,
        subscription_id=subscription.id,
        idempotency_key="ext-idem-1",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()
    await db_session.refresh(payment)
    await payment_service.attach_provider_payment_id(
        payment_id=payment.id, provider_payment_id="yk-ext-1"
    )
    await db_session.commit()

    # Плоский metadata, который реально возвращает YooKassa в webhook —
    # именно то, что build_yookassa_flat_metadata отправила бы при создании.
    webhook_payload = {
        "object": {
            "id": "yk-ext-1",
            "amount": {"value": "299.00", "currency": "RUB"},
            "paid": True,
            "description": f"FastLink payment #{payment.id}",
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {
                "tariff_id": str(tariff.id),
                "server_id": str(server.id),
                "marzban_username": subscription.marzban_username,
                "expires_at": subscription.expires_at.isoformat(),
                "subscription_id": str(subscription.id),
            },
        }
    }
    fake_event = type(
        "FakeEvent",
        (),
        {"id": 1, "provider": "yookassa", "event_type": "payment.succeeded"},
    )()

    await _handle_payment_succeeded(db_session, fake_event, webhook_payload, bot=None)
    await db_session.commit()

    result = await db_session.execute(
        select(Subscription).where(Subscription.id == subscription.id)
    )
    updated: Subscription = result.scalars().one()

    expected_expires_at = old_expires_at + timedelta(days=tariff.duration_days)
    assert abs((updated.expires_at - expected_expires_at).total_seconds()) < 2
    assert updated.data_used_bytes == 0
    assert updated.data_limit_bytes == tariff.data_limit_bytes


@pytest.mark.asyncio
async def test_extension_reactivates_expired_disabled_subscription(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(
        "services.marzban_subscription.SubscriptionMarzbanService.set_enabled",
        _fake_set_enabled,
    )

    user, server, tariff, subscription = await _make_active_subscription(
        db_session, days_left=-3
    )
    subscription.status = SubscriptionStatus.DISABLED
    subscription.disabled_reason = DisabledReason.EXPIRED
    db_session.add(subscription)
    await db_session.commit()

    payment_service = PaymentService(db_session)
    metadata_snapshot = _build_extension_metadata_snapshot(
        user, server, tariff, subscription
    )
    payment = await payment_service.create_payment(
        user_id=user.id,
        amount=tariff.price_amount,
        currency=tariff.price_currency,
        provider=PaymentProvider.YOOKASSA,
        subscription_id=subscription.id,
        idempotency_key="ext-idem-2",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()
    await payment_service.attach_provider_payment_id(
        payment_id=payment.id, provider_payment_id="yk-ext-2"
    )
    await db_session.commit()

    webhook_payload = {
        "object": {
            "id": "yk-ext-2",
            "amount": {"value": "299.00", "currency": "RUB"},
            "paid": True,
            "description": f"FastLink payment #{payment.id}",
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {
                "tariff_id": str(tariff.id),
                "server_id": str(server.id),
                "marzban_username": subscription.marzban_username,
                "expires_at": subscription.expires_at.isoformat(),
                "subscription_id": str(subscription.id),
            },
        }
    }
    fake_event = type(
        "FakeEvent",
        (),
        {"id": 2, "provider": "yookassa", "event_type": "payment.succeeded"},
    )()

    await _handle_payment_succeeded(db_session, fake_event, webhook_payload, bot=None)
    await db_session.commit()

    result = await db_session.execute(
        select(Subscription).where(Subscription.id == subscription.id)
    )
    updated: Subscription = result.scalars().one()

    assert updated.status is SubscriptionStatus.ACTIVE
    assert updated.disabled_reason is None
    assert updated.expires_at > datetime.now(UTC)
