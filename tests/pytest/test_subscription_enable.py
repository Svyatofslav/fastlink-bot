from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from database.enums import DisabledReason, SubscriptionStatus
from database.models import Server, Subscription, Tariff, User
from database.repo.admin_actions import AdminActionRepo
from services.subscription import SubscriptionService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_disabled_subscription(
    db_session: AsyncSession, suffix: str
) -> Subscription:
    user = User(telegram_id=600_000_000 + abs(hash(suffix)) % 90_000_000)
    server = Server(
        name=f"enable-server-{suffix}",
        inbound_tag=f"enable-inbound-{suffix}",
    )
    tariff = Tariff(
        server_id=None,
        name=f"Enable tariff {suffix}",
        duration_days=30,
        data_limit_bytes=10_000_000,
        price_amount=10000,
    )
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    now = datetime.now(UTC)
    subscription = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username=f"to-enable-{suffix}",
        status=SubscriptionStatus.DISABLED,
        starts_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=20),
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url=f"https://example.com/sub/to-enable-{suffix}",
        disabled_reason=DisabledReason.EXPIRED,
    )
    db_session.add(subscription)
    await db_session.commit()
    return subscription


@pytest.mark.asyncio
async def test_enable_clears_disabled_reason_and_sets_active(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    SubscriptionService.enable должен вернуть подписку в ACTIVE и
    очистить disabled_reason (обратный переход к
    test_disable_sets_disabled_status_and_reason из test_subscription_jobs.py).
    """
    service = SubscriptionService(db_session)
    subscription = await _make_disabled_subscription(db_session, "basic")

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

    updated = await service.enable(subscription_id=subscription.id, admin_id=None)

    assert updated.status is SubscriptionStatus.ACTIVE
    assert updated.disabled_reason is None

    result = await db_session.execute(
        select(Subscription).where(Subscription.id == subscription.id)
    )
    loaded: Subscription = result.scalars().one()
    assert loaded.status is SubscriptionStatus.ACTIVE
    assert loaded.disabled_reason is None


@pytest.mark.asyncio
async def test_enable_logs_admin_action_when_admin_id_provided(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    Если enable вызывается с admin_id (ручное включение админом),
    должна создаваться запись AdminActionLog с ENABLE_SUBSCRIPTION.
    """
    from database.enums import AdminActionType
    from database.models import Admin

    service = SubscriptionService(db_session)
    subscription = await _make_disabled_subscription(db_session, "withadmin")

    admin = Admin(
        telegram_id=700_000_001,
        username="ops",
        login="ops-admin",
        password_hash="x",
        secretword_hash="x",
        is_superadmin=False,
    )
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()

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
        sub.status = SubscriptionStatus.ACTIVE
        sub.disabled_reason = None
        db_session.add(sub)
        await db_session.flush()
        await db_session.refresh(sub)
        return sub

    monkeypatch.setattr(
        "services.marzban_subscription.SubscriptionMarzbanService.set_enabled",
        fake_set_enabled,
    )

    await service.enable(subscription_id=subscription.id, admin_id=admin.id)

    actions_repo = AdminActionRepo(db_session)
    actions = await actions_repo.get_by_admin(admin.id)

    assert len(actions) == 1
    assert actions[0].action is AdminActionType.ENABLE_SUBSCRIPTION
    assert actions[0].entity_id == subscription.id
