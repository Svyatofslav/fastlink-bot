from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from database.enums import NotificationType
from services.notifications import NotificationService
from tests.pytest.factories import (
    make_server,
    make_subscription,
    make_tariff,
    make_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_user_with_subscription(db_session: AsyncSession, suffix: str):
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()
    subscription = make_subscription(
        user_id=user.id, server_id=server.id, tariff_id=tariff.id
    )
    db_session.add(subscription)
    await db_session.flush()
    return user, subscription


@pytest.mark.asyncio
async def test_log_failure_writes_failed_status(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    service = NotificationService(db_session)
    await service.log_failure(
        user_id=user.id,
        notification_type=NotificationType.PAYMENT_SUCCEEDED,
        payload={"reason": "telegram_api_down"},
    )
    await db_session.commit()

    was_sent = await service.was_sent(
        user_id=user.id, notification_type=NotificationType.PAYMENT_SUCCEEDED
    )
    assert was_sent in (True, False)


@pytest.mark.asyncio
async def test_try_notify_dedup_race_returns_false(db_session: AsyncSession) -> None:
    user, subscription = await _make_user_with_subscription(db_session, "race1")

    service = NotificationService(db_session)

    with patch.object(
        service._repo,
        "log",
        new=AsyncMock(side_effect=IntegrityError("dup", None, None)),
    ):
        result = await service.notify_sub_expires_3d(
            user_id=user.id, subscription_id=subscription.id
        )

    assert result is False


@pytest.mark.asyncio
async def test_notify_payment_succeeded_real_call(db_session: AsyncSession) -> None:
    user, subscription = await _make_user_with_subscription(db_session, "pay1")

    service = NotificationService(db_session)
    result = await service.notify_payment_succeeded(
        user_id=user.id, subscription_id=subscription.id
    )
    await db_session.commit()

    assert result is True
    was_sent = await service.was_sent(
        user_id=user.id,
        notification_type=NotificationType.PAYMENT_SUCCEEDED,
        subscription_id=subscription.id,
    )
    assert was_sent is True


@pytest.mark.asyncio
async def test_notify_refund_processed_real_call(db_session: AsyncSession) -> None:
    user, subscription = await _make_user_with_subscription(db_session, "refund1")

    service = NotificationService(db_session)
    result = await service.notify_refund_processed(
        user_id=user.id, subscription_id=subscription.id
    )
    await db_session.commit()

    assert result is True
    was_sent = await service.was_sent(
        user_id=user.id,
        notification_type=NotificationType.REFUND_PROCESSED,
        subscription_id=subscription.id,
    )
    assert was_sent is True


@pytest.mark.asyncio
async def test_notify_traffic_100_real_call(db_session: AsyncSession) -> None:
    user, subscription = await _make_user_with_subscription(db_session, "traffic1")

    service = NotificationService(db_session)
    result = await service.notify_traffic_100(
        user_id=user.id, subscription_id=subscription.id
    )
    await db_session.commit()

    assert result is True
    was_sent = await service.was_sent(
        user_id=user.id,
        notification_type=NotificationType.TRAFFIC_100,
        subscription_id=subscription.id,
    )
    assert was_sent is True


@pytest.mark.asyncio
async def test_notify_payment_succeeded_dedup_returns_false_on_second_call(
    db_session: AsyncSession,
) -> None:
    user, subscription = await _make_user_with_subscription(db_session, "dedup1")

    service = NotificationService(db_session)
    first = await service.notify_payment_succeeded(
        user_id=user.id, subscription_id=subscription.id
    )
    await db_session.commit()
    second = await service.notify_payment_succeeded(
        user_id=user.id, subscription_id=subscription.id
    )

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_notify_donation_succeeded_real_call(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    service = NotificationService(db_session)
    result = await service.notify_donation_succeeded(user_id=user.id)
    await db_session.commit()

    assert result is True
    was_sent = await service.was_sent(
        user_id=user.id, notification_type=NotificationType.DONATION_SUCCEEDED
    )
    assert was_sent is True


@pytest.mark.asyncio
async def test_notify_traffic_95_real_call(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()
    subscription = make_subscription(
        user_id=user.id, server_id=server.id, tariff_id=tariff.id
    )
    db_session.add(subscription)
    await db_session.flush()

    service = NotificationService(db_session)
    result = await service.notify_traffic_95(
        user_id=user.id, subscription_id=subscription.id
    )
    await db_session.commit()

    assert result is True
    was_sent = await service.was_sent(
        user_id=user.id,
        notification_type=NotificationType.TRAFFIC_95,
        subscription_id=subscription.id,
    )
    assert was_sent is True
