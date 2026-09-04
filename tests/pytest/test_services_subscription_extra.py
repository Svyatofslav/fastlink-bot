from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from database.enums import DisabledReason, SubscriptionStatus
from database.repo.servers import ServerRepo
from database.repo.subscriptions import SubscriptionRepo
from database.repo.tariffs import TariffRepo
from database.repo.users import UserRepo
from services.subscription import SubscriptionService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_base(db_session: AsyncSession, suffix: str):
    users = UserRepo(db_session)
    servers = ServerRepo(db_session)
    tariffs = TariffRepo(db_session)

    user = await users.create(
        telegram_id=hash(suffix) % 1_000_000_000 + 600_000_000,
        username=f"user_{suffix}",
        first_name="Test",
        last_name="User",
        language_code="ru",
    )
    server = await servers.create(
        name=f"server-{suffix}",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag=f"inbound-{suffix}",
        sort_order=100,
        is_active=True,
    )
    tariff = await tariffs.create(
        server_id=server.id,
        name=f"tariff-{suffix}",
        duration_days=30,
        data_limit_bytes=10_000,
        price_amount=1000,
    )
    await db_session.commit()
    return user, server, tariff


# ---------------------------------------------------------------------------
# create_for_payment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_for_payment_user_not_found_raises(
    db_session: AsyncSession,
) -> None:
    _user, server, tariff = await _make_base(db_session, "cfp-unf")
    service = SubscriptionService(db_session)

    with pytest.raises(ValueError, match="User 999999 not found"):
        await service.create_for_payment(
            user_id=999999,
            tariff_id=tariff.id,
            server_id=server.id,
            marzban_username="mz-unf",
            starts_at=None,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )


@pytest.mark.asyncio
async def test_create_for_payment_tariff_not_found_raises(
    db_session: AsyncSession,
) -> None:
    user, server, _tariff = await _make_base(db_session, "cfp-tnf")
    service = SubscriptionService(db_session)

    with pytest.raises(ValueError, match="Tariff 999999 not found"):
        await service.create_for_payment(
            user_id=user.id,
            tariff_id=999999,
            server_id=server.id,
            marzban_username="mz-tnf",
            starts_at=None,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )


@pytest.mark.asyncio
async def test_create_for_payment_success(db_session: AsyncSession) -> None:
    user, server, tariff = await _make_base(db_session, "cfp-ok")
    service = SubscriptionService(db_session)
    expires_at = datetime.now(UTC) + timedelta(days=30)

    subscription = await service.create_for_payment(
        user_id=user.id,
        tariff_id=tariff.id,
        server_id=server.id,
        marzban_username="mz-ok",
        starts_at=None,
        expires_at=expires_at,
    )

    assert subscription.status == SubscriptionStatus.PENDING
    assert subscription.data_limit_bytes == tariff.data_limit_bytes
    assert subscription.data_used_bytes == 0
    assert subscription.marzban_username == "mz-ok"


# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_delegates_to_marzban_service(db_session: AsyncSession) -> None:
    service = SubscriptionService(db_session)
    fake_result = MagicMock()
    service._marzban.activate_subscription = AsyncMock(return_value=fake_result)

    result = await service.activate(subscription_id=42)

    assert result is fake_result
    service._marzban.activate_subscription.assert_awaited_once_with(42)


# ---------------------------------------------------------------------------
# disable / enable — с admin_id (аудит)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disable_with_admin_id_logs_audit(db_session: AsyncSession) -> None:
    service = SubscriptionService(db_session)
    fake_subscription = MagicMock(
        id=1,
        status=SubscriptionStatus.DISABLED,
        disabled_reason=DisabledReason.EXPIRED,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=0,
    )
    service._marzban.set_enabled = AsyncMock(return_value=fake_subscription)
    service._admin_actions.log_subscription_change = AsyncMock()

    result = await service.disable(
        subscription_id=1, disabled_reason=DisabledReason.EXPIRED, admin_id=99
    )

    assert result is fake_subscription
    service._admin_actions.log_subscription_change.assert_awaited_once()
    call_kwargs = service._admin_actions.log_subscription_change.await_args.kwargs
    assert call_kwargs["admin_id"] == 99
    assert call_kwargs["subscription_id"] == 1


@pytest.mark.asyncio
async def test_disable_without_admin_id_skips_audit(db_session: AsyncSession) -> None:
    service = SubscriptionService(db_session)
    fake_subscription = MagicMock()
    service._marzban.set_enabled = AsyncMock(return_value=fake_subscription)
    service._admin_actions.log_subscription_change = AsyncMock()

    await service.disable(
        subscription_id=1, disabled_reason=DisabledReason.EXPIRED, admin_id=None
    )

    service._admin_actions.log_subscription_change.assert_not_awaited()


@pytest.mark.asyncio
async def test_enable_with_admin_id_logs_audit(db_session: AsyncSession) -> None:
    service = SubscriptionService(db_session)
    fake_subscription = MagicMock(
        id=1,
        status=SubscriptionStatus.ACTIVE,
        disabled_reason=None,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=0,
    )
    service._marzban.set_enabled = AsyncMock(return_value=fake_subscription)
    service._admin_actions.log_subscription_change = AsyncMock()

    result = await service.enable(subscription_id=1, admin_id=7)

    assert result is fake_subscription
    service._admin_actions.log_subscription_change.assert_awaited_once()
    call_kwargs = service._admin_actions.log_subscription_change.await_args.kwargs
    assert call_kwargs["admin_id"] == 7


@pytest.mark.asyncio
async def test_enable_without_admin_id_skips_audit(db_session: AsyncSession) -> None:
    service = SubscriptionService(db_session)
    fake_subscription = MagicMock()
    service._marzban.set_enabled = AsyncMock(return_value=fake_subscription)
    service._admin_actions.log_subscription_change = AsyncMock()

    await service.enable(subscription_id=1, admin_id=None)

    service._admin_actions.log_subscription_change.assert_not_awaited()


# ---------------------------------------------------------------------------
# extend_for_payment — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extend_for_payment_subscription_not_found_raises(
    db_session: AsyncSession,
) -> None:
    _user, _server, tariff = await _make_base(db_session, "ext-snf")
    service = SubscriptionService(db_session)

    with pytest.raises(ValueError, match="Subscription 999999 not found"):
        await service.extend_for_payment(subscription_id=999999, tariff_id=tariff.id)


@pytest.mark.asyncio
async def test_extend_for_payment_tariff_not_found_raises(
    db_session: AsyncSession,
) -> None:
    user, server, tariff = await _make_base(db_session, "ext-tnf")
    subs = SubscriptionRepo(db_session)
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="mz-ext-tnf",
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=datetime.now(UTC) + timedelta(days=10),
        data_limit_bytes=1000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="https://example.com/sub/ext-tnf",
        disabled_reason=None,
    )
    await db_session.commit()
    service = SubscriptionService(db_session)

    with pytest.raises(ValueError, match="Tariff 999999 not found"):
        await service.extend_for_payment(
            subscription_id=subscription.id, tariff_id=999999
        )


@pytest.mark.asyncio
async def test_extend_for_payment_reenables_previously_expired_subscription(
    db_session: AsyncSession,
) -> None:
    user, server, tariff = await _make_base(db_session, "ext-reenable")
    subs = SubscriptionRepo(db_session)
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="mz-ext-reenable",
        status=SubscriptionStatus.DISABLED,
        starts_at=None,
        expires_at=datetime.now(UTC) - timedelta(days=1),
        data_limit_bytes=1000,
        data_used_bytes=1000,
        auto_renew=False,
        subscription_url="https://example.com/sub/ext-reenable",
        disabled_reason=DisabledReason.EXPIRED,
    )
    await db_session.commit()

    service = SubscriptionService(db_session)
    reenabled = MagicMock(status=SubscriptionStatus.ACTIVE)
    service._marzban.set_enabled = AsyncMock(return_value=reenabled)

    result = await service.extend_for_payment(
        subscription_id=subscription.id, tariff_id=tariff.id
    )

    assert result is reenabled
    service._marzban.set_enabled.assert_awaited_once_with(
        subscription_id=subscription.id, enabled=True, disabled_reason=None
    )


@pytest.mark.asyncio
async def test_extend_for_payment_active_subscription_does_not_call_marzban(
    db_session: AsyncSession,
) -> None:
    user, server, tariff = await _make_base(db_session, "ext-active")
    subs = SubscriptionRepo(db_session)
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="mz-ext-active",
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=datetime.now(UTC) + timedelta(days=5),
        data_limit_bytes=1000,
        data_used_bytes=500,
        auto_renew=False,
        subscription_url="https://example.com/sub/ext-active",
        disabled_reason=None,
    )
    await db_session.commit()

    service = SubscriptionService(db_session)
    service._marzban.set_enabled = AsyncMock()

    await service.extend_for_payment(
        subscription_id=subscription.id, tariff_id=tariff.id
    )

    service._marzban.set_enabled.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_traffic_with_notifications — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_traffic_with_notifications_not_found_raises(
    db_session: AsyncSession,
) -> None:
    service = SubscriptionService(db_session)

    with pytest.raises(ValueError, match="Subscription 999999 not found"):
        await service.update_traffic_with_notifications(
            subscription_id=999999, data_used_bytes=100
        )
