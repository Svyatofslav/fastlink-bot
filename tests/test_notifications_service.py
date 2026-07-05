from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import (
    NotificationType,
    NotificationDeliveryStatus,
    SubscriptionStatus,
)
from database.models import User, Subscription, Server, Tariff
from database.repo.notifications import NotificationRepo
from services.notifications import NotificationService


@pytest.mark.asyncio
async def test_should_send_false_when_already_sent(db_session: AsyncSession) -> None:
    """
    should_send == False, если запись уже есть в notifications_log.
    """
    repo = NotificationRepo(db_session)
    service = NotificationService(db_session)

    # создаём пользователя и подписку, чтобы FK прошли
    user = User(telegram_id=777_777_777)
    server = Server(
        name="notif-server",
        country_code=None,
        country_name=None,
        emoji=None,
        api_url="https://example.com/api",
        api_token="test-token",
        metrics_url=None,
        metrics_token=None,
        inbound_tag="notif-inbound",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Notif tariff",
        duration_days=30,
        data_limit_bytes=1_000_000,
        price_amount=100_00,
        price_currency="RUB",
        is_active=True,
        sort_order=100,
        description=None,
    )

    db_session.add_all([user, server, tariff])
    await db_session.flush()

    subscription = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="notif-user",
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=tariff.data_limit_bytes,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/notif-user",
        disabled_reason=None,
    )

    db_session.add(subscription)
    await db_session.flush()

    user_id = user.id
    subscription_id = subscription.id

    # Создаём запись как будто уведомление уже было отправлено
    await repo.log(
        user_id=user_id,
        notification_type=NotificationType.TRAFFIC_80,
        delivery_status=NotificationDeliveryStatus.SENT,
        subscription_id=subscription_id,
        payload={"test": "payload"},
    )

    should = await service.should_send(
        user_id=user_id,
        notification_type=NotificationType.TRAFFIC_80,
        subscription_id=subscription_id,
    )
    assert should is False

    # Для другого типа должно быть True
    should_other = await service.should_send(
        user_id=user_id,
        notification_type=NotificationType.TRAFFIC_95,
        subscription_id=subscription_id,
    )
    assert should_other is True

    # Для другого subscription_id тоже True
    should_other_sub = await service.should_send(
        user_id=user_id,
        notification_type=NotificationType.TRAFFIC_80,
        subscription_id=subscription_id + 1,
    )
    assert should_other_sub is True


@pytest.mark.asyncio
async def test_notify_traffic_80_respects_deduplication(
    db_session: AsyncSession,
) -> None:
    """
    notify_traffic_80: первая отправка логируется, повторная — отфильтровывается.
    """
    repo = NotificationRepo(db_session)
    service = NotificationService(db_session)

    # создаём пользователя и подписку
    user = User(telegram_id=888_888_888)
    server = Server(
        name="traffic-notif-server",
        country_code=None,
        country_name=None,
        emoji=None,
        api_url="https://example.com/api",
        api_token="test-token",
        metrics_url=None,
        metrics_token=None,
        inbound_tag="traffic-notif-inbound",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Traffic notif tariff",
        duration_days=30,
        data_limit_bytes=1_000_000,
        price_amount=100_00,
        price_currency="RUB",
        is_active=True,
        sort_order=100,
        description=None,
    )

    db_session.add_all([user, server, tariff])
    await db_session.flush()

    subscription = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="traffic-notif-user",
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=tariff.data_limit_bytes,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/traffic-notif-user",
        disabled_reason=None,
    )

    db_session.add(subscription)
    await db_session.flush()

    user_id = user.id
    subscription_id = subscription.id

    # Первая попытка — должно быть True и должна появиться запись
    first = await service.notify_traffic_80(
        user_id=user_id,
        subscription_id=subscription_id,
        payload={"first": True},
    )
    assert first is True

    logs = await repo.get_by_user(user_id=user_id)
    types = [log.type for log in logs]
    assert NotificationType.TRAFFIC_80 in types

    # Вторая попытка — should_send вернёт False, notify_* вернёт False
    second = await service.notify_traffic_80(
        user_id=user_id,
        subscription_id=subscription_id,
        payload={"second": True},
    )
    assert second is False

    logs_after = await repo.get_by_user(user_id=user_id)
    types_after = [log.type for log in logs_after]
    assert types_after.count(NotificationType.TRAFFIC_80) == 1


@pytest.mark.asyncio
async def test_notify_sub_expires_3d_and_1d_respect_deduplication(
    db_session: AsyncSession,
) -> None:
    """
    notify_sub_expires_3d/1d: первая отправка логируется, повторная — отфильтровывается.
    """
    repo = NotificationRepo(db_session)
    service = NotificationService(db_session)

    # создаём пользователя и подписку
    user = User(telegram_id=999_999_999)
    server = Server(
        name="expires-notif-server",
        country_code=None,
        country_name=None,
        emoji=None,
        api_url="https://example.com/api",
        api_token="test-token",
        metrics_url=None,
        metrics_token=None,
        inbound_tag="expires-notif-inbound",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Expires notif tariff",
        duration_days=30,
        data_limit_bytes=1_000_000,
        price_amount=100_00,
        price_currency="RUB",
        is_active=True,
        sort_order=100,
        description=None,
    )

    db_session.add_all([user, server, tariff])
    await db_session.flush()

    subscription = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="expires-notif-user",
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=tariff.data_limit_bytes,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/expires-notif-user",
        disabled_reason=None,
    )

    db_session.add(subscription)
    await db_session.flush()

    user_id = user.id
    subscription_id = subscription.id

    # 3 дня до окончания: первая отправка — True + лог
    first_3d = await service.notify_sub_expires_3d(
        user_id=user_id,
        subscription_id=subscription_id,
        payload={"days": 3},
    )
    assert first_3d is True

    logs = await repo.get_by_user(user_id=user_id)
    types = [log.type for log in logs]
    assert NotificationType.SUB_EXPIRES_3D in types

    # Повтор 3d — False и без новых записей
    second_3d = await service.notify_sub_expires_3d(
        user_id=user_id,
        subscription_id=subscription_id,
        payload={"days": 3, "repeat": True},
    )
    assert second_3d is False

    logs_after_3d = await repo.get_by_user(user_id=user_id)
    types_after_3d = [log.type for log in logs_after_3d]
    assert types_after_3d.count(NotificationType.SUB_EXPIRES_3D) == 1

    # 1 день до окончания: отдельный тип — первая отправка должна пройти
    first_1d = await service.notify_sub_expires_1d(
        user_id=user_id,
        subscription_id=subscription_id,
        payload={"days": 1},
    )
    assert first_1d is True

    logs_after_1d = await repo.get_by_user(user_id=user_id)
    types_after_1d = [log.type for log in logs_after_1d]
    assert NotificationType.SUB_EXPIRES_1D in types_after_1d

    # Повтор 1d — False и без новых записей
    second_1d = await service.notify_sub_expires_1d(
        user_id=user_id,
        subscription_id=subscription_id,
        payload={"days": 1, "repeat": True},
    )
    assert second_1d is False

    logs_final = await repo.get_by_user(user_id=user_id)
    types_final = [log.type for log in logs_final]
    assert types_final.count(NotificationType.SUB_EXPIRES_3D) == 1
    assert types_final.count(NotificationType.SUB_EXPIRES_1D) == 1
