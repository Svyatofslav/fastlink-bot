# tests/test_subscription_jobs.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from database.enums import DisabledReason, SubscriptionStatus
from database.models import Server, Subscription, Tariff, User
from database.repo.subscriptions import SubscriptionRepo
from services.subscription import SubscriptionService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _utc_now() -> datetime:
    # БД и модели у тебя timezone-aware, так что лучше явно использовать UTC.
    return datetime.now(UTC)


@pytest.mark.asyncio
async def test_get_expired_returns_only_overdue_active(
    db_session: AsyncSession,
) -> None:
    """
    SubscriptionRepo.get_expired должен возвращать только ACTIVE-подписки,
    у которых expires_at <= now.
    """
    repo = SubscriptionRepo(db_session)

    user = User(telegram_id=111_111_111)
    server = Server(
        name="expired-server",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="expired-inbound",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Expired tariff",
        duration_days=30,
        data_limit_bytes=10_000_000,
        price_amount=100_00,
        price_currency="RUB",
        is_active=True,
        sort_order=100,
        description=None,
    )

    db_session.add_all([user, server, tariff])
    await db_session.flush()

    now = _utc_now()

    expired_sub = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="expired-user",
        status=SubscriptionStatus.ACTIVE,
        starts_at=now - timedelta(days=30),
        expires_at=now - timedelta(days=1),
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/expired-user",
        disabled_reason=None,
    )

    future_sub = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="future-user",
        status=SubscriptionStatus.ACTIVE,
        starts_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=3),
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/future-user",
        disabled_reason=None,
    )

    db_session.add_all([expired_sub, future_sub])
    await db_session.commit()

    expired_list = await repo.get_expired()

    ids = {s.id for s in expired_list}
    assert expired_sub.id in ids
    assert future_sub.id not in ids


@pytest.mark.asyncio
async def test_get_expiring_within_days_excludes_expired(
    db_session: AsyncSession,
) -> None:
    """
    SubscriptionRepo.get_expiring(within_days) должен возвращать только ACTIVE-подписки
    с expires_at в указанном окне ( > now и <= now + N дней ).
    """
    repo = SubscriptionRepo(db_session)

    user = User(telegram_id=222_222_222)
    server = Server(
        name="window-server",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="window-inbound",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Window tariff",
        duration_days=30,
        data_limit_bytes=10_000_000,
        price_amount=100_00,
        price_currency="RUB",
        is_active=True,
        sort_order=100,
        description=None,
    )

    db_session.add_all([user, server, tariff])
    await db_session.flush()

    now = _utc_now()

    in_window = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="in-window",
        status=SubscriptionStatus.ACTIVE,
        starts_at=now - timedelta(days=27),
        expires_at=now + timedelta(days=2),
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/in-window",
        disabled_reason=None,
    )

    out_window = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="out-window",
        status=SubscriptionStatus.ACTIVE,
        starts_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=10),
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/out-window",
        disabled_reason=None,
    )

    already_expired = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="already-expired",
        status=SubscriptionStatus.ACTIVE,
        starts_at=now - timedelta(days=30),
        expires_at=now - timedelta(days=1),
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/already-expired",
        disabled_reason=None,
    )

    db_session.add_all([in_window, out_window, already_expired])
    await db_session.commit()

    expiring_list = await repo.get_expiring(within_days=3)
    ids = {s.id for s in expiring_list}

    assert in_window.id in ids
    assert out_window.id not in ids
    assert already_expired.id not in ids


@pytest.mark.asyncio
async def test_disable_sets_disabled_status_and_reason(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    SubscriptionService.disable должен поставить статус DISABLED и DisabledReason.EXPIRED.
    Marzban-клиент внутри мы замокаем, чтобы не трогать внешний API.
    """
    service = SubscriptionService(db_session)

    user = User(telegram_id=333_333_333)
    server = Server(
        name="disable-server",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="disable-inbound",
        is_active=True,
        sort_order=100,
    )
    tariff = Tariff(
        server_id=None,
        name="Disable tariff",
        duration_days=30,
        data_limit_bytes=10_000_000,
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
        marzban_username="to-disable",
        status=SubscriptionStatus.ACTIVE,
        starts_at=_utc_now() - timedelta(days=30),
        expires_at=_utc_now() - timedelta(days=1),
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/to-disable",
        disabled_reason=None,
    )

    db_session.add(subscription)
    await db_session.commit()

    # Мокаем SubscriptionMarzbanService.set_enabled так, чтобы он просто
    # обновил статус/disabled_reason в самой подписке, не ходя в HTTP.

    async def fake_set_enabled(
        self,
        *,
        subscription_id: int,
        enabled: bool,
        disabled_reason: DisabledReason | None,
    ) -> Subscription:
        result = await db_session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        sub: Subscription = result.scalars().one()
        if enabled:
            sub.status = SubscriptionStatus.ACTIVE
            sub.disabled_reason = None
        else:
            sub.status = SubscriptionStatus.DISABLED
            sub.disabled_reason = disabled_reason
        db_session.add(sub)
        await db_session.flush()
        await db_session.refresh(sub)
        return sub

    monkeypatch.setattr(
        "services.marzban_subscription.SubscriptionMarzbanService.set_enabled",
        fake_set_enabled,
    )

    updated = await service.disable(
        subscription_id=subscription.id,
        disabled_reason=DisabledReason.EXPIRED,
        admin_id=None,
    )

    assert updated.status is SubscriptionStatus.DISABLED
    assert updated.disabled_reason is DisabledReason.EXPIRED

    result = await db_session.execute(
        select(Subscription).where(Subscription.id == subscription.id)
    )
    loaded: Subscription = result.scalars().one()

    assert loaded.status is SubscriptionStatus.DISABLED
    assert loaded.disabled_reason is DisabledReason.EXPIRED
