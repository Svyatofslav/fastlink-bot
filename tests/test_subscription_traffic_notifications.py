from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import SubscriptionStatus
from database.models import User, Server, Tariff, Subscription
from services.subscription import SubscriptionService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_update_traffic_triggers_80_percent_notification(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    При ~80% использования вызывается только notify_traffic_80.
    """
    service = SubscriptionService(db_session)

    user = User(telegram_id=444_444_444)
    server = Server(
        name="traffic-server",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="traffic-inbound",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Traffic tariff",
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
        marzban_username="traffic-user",
        status=SubscriptionStatus.ACTIVE,
        starts_at=_utc_now() - timedelta(days=1),
        expires_at=_utc_now() + timedelta(days=29),
        data_limit_bytes=tariff.data_limit_bytes,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/traffic-user",
        disabled_reason=None,
    )

    db_session.add(subscription)
    await db_session.commit()

    # Мокаем Marzban sync_traffic: он просто обновляет data_used_bytes.
    async def fake_sync_traffic(
        self, *, subscription_id: int, data_used_bytes: int
    ) -> Subscription:
        sub = await db_session.get(Subscription, subscription_id)
        sub.data_used_bytes = data_used_bytes
        db_session.add(sub)
        await db_session.flush()
        await db_session.refresh(sub)
        return sub

    # Мокаем NotificationService.notify_traffic_80/95/100, чтобы считать вызовы.
    calls_80: list[tuple[int, int]] = []
    calls_95: list[tuple[int, int]] = []
    calls_100: list[tuple[int, int]] = []

    async def fake_notify_traffic_80(
        self, *, user_id: int, subscription_id: int, payload: dict | None = None
    ) -> bool:
        calls_80.append((user_id, subscription_id))
        return True

    async def fake_notify_traffic_95(
        self, *, user_id: int, subscription_id: int, payload: dict | None = None
    ) -> bool:
        calls_95.append((user_id, subscription_id))
        return True

    async def fake_notify_traffic_100(
        self, *, user_id: int, subscription_id: int, payload: dict | None = None
    ) -> bool:
        calls_100.append((user_id, subscription_id))
        return True

    monkeypatch.setattr(
        "services.marzban_subscription.SubscriptionMarzbanService.sync_traffic",
        fake_sync_traffic,
    )
    monkeypatch.setattr(
        "services.notifications.NotificationService.notify_traffic_80",
        fake_notify_traffic_80,
    )
    monkeypatch.setattr(
        "services.notifications.NotificationService.notify_traffic_95",
        fake_notify_traffic_95,
    )
    monkeypatch.setattr(
        "services.notifications.NotificationService.notify_traffic_100",
        fake_notify_traffic_100,
    )

    # 79% — ничего не должно отправиться
    await service.update_traffic_with_notifications(
        subscription_id=subscription.id,
        data_used_bytes=int(tariff.data_limit_bytes * 79 // 100),
    )
    assert calls_80 == []
    assert calls_95 == []
    assert calls_100 == []

    # 85% — только notify_traffic_80
    await service.update_traffic_with_notifications(
        subscription_id=subscription.id,
        data_used_bytes=int(tariff.data_limit_bytes * 85 // 100),
    )
    assert calls_80 == [(user.id, subscription.id)]
    assert calls_95 == []
    assert calls_100 == []


@pytest.mark.asyncio
async def test_update_traffic_triggers_95_and_100_percent_notifications(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    При ~95% вызывается notify_traffic_95, при >=100% — notify_traffic_100.
    """
    service = SubscriptionService(db_session)

    user = User(telegram_id=555_555_555)
    server = Server(
        name="traffic-server-2",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="traffic-inbound-2",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Traffic tariff 2",
        duration_days=30,
        data_limit_bytes=2_000_000,
        price_amount=200_00,
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
        marzban_username="traffic-user-2",
        status=SubscriptionStatus.ACTIVE,
        starts_at=_utc_now() - timedelta(days=1),
        expires_at=_utc_now() + timedelta(days=29),
        data_limit_bytes=tariff.data_limit_bytes,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/traffic-user-2",
        disabled_reason=None,
    )

    db_session.add(subscription)
    await db_session.commit()

    async def fake_sync_traffic(
        self, *, subscription_id: int, data_used_bytes: int
    ) -> Subscription:
        sub = await db_session.get(Subscription, subscription_id)
        sub.data_used_bytes = data_used_bytes
        db_session.add(sub)
        await db_session.flush()
        await db_session.refresh(sub)
        return sub

    calls_95: list[tuple[int, int]] = []
    calls_100: list[tuple[int, int]] = []

    async def fake_notify_traffic_95(
        self, *, user_id: int, subscription_id: int, payload: dict | None = None
    ) -> bool:
        calls_95.append((user_id, subscription_id))
        return True

    async def fake_notify_traffic_100(
        self, *, user_id: int, subscription_id: int, payload: dict | None = None
    ) -> bool:
        calls_100.append((user_id, subscription_id))
        return True

    monkeypatch.setattr(
        "services.marzban_subscription.SubscriptionMarzbanService.sync_traffic",
        fake_sync_traffic,
    )
    monkeypatch.setattr(
        "services.notifications.NotificationService.notify_traffic_95",
        fake_notify_traffic_95,
    )
    monkeypatch.setattr(
        "services.notifications.NotificationService.notify_traffic_100",
        fake_notify_traffic_100,
    )

    # 97% — только 95-порог
    await service.update_traffic_with_notifications(
        subscription_id=subscription.id,
        data_used_bytes=int(tariff.data_limit_bytes * 97 // 100),
    )
    assert calls_95 == [(user.id, subscription.id)]
    assert calls_100 == []

    # 120% — только 100-порог (новый вызов)
    await service.update_traffic_with_notifications(
        subscription_id=subscription.id,
        data_used_bytes=int(tariff.data_limit_bytes * 120 // 100),
    )
    assert calls_100 == [(user.id, subscription.id)]
