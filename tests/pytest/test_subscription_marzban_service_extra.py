from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from clients.marzban import MarzbanClient, MarzbanUserInfo
from database.enums import DisabledReason, SubscriptionStatus
from database.repo.servers import ServerRepo
from database.repo.subscriptions import SubscriptionRepo
from database.repo.tariffs import TariffRepo
from database.repo.users import UserRepo
from services.marzban_subscription import SubscriptionMarzbanService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_subscription(db_session: AsyncSession, *, suffix: str):
    servers = ServerRepo(session=db_session)
    tariffs = TariffRepo(session=db_session)
    subs = SubscriptionRepo(session=db_session)
    users = UserRepo(session=db_session)

    user = await users.create(
        telegram_id=hash(suffix) % 1_000_000_000 + 500_000_000,
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
        data_limit_bytes=1000,
        price_amount=100,
    )
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username=f"mz-{suffix}",
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url=f"https://example.com/sub/{suffix}",
        disabled_reason=None,
    )
    await db_session.commit()
    return subscription


# ---------------------------------------------------------------------------
# activate_subscription — недостающие not-found ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_subscription_not_found_raises(db_session: AsyncSession) -> None:
    service = SubscriptionMarzbanService(session=db_session)

    with pytest.raises(ValueError, match="Subscription 999999 not found"):
        await service.activate_subscription(999999)


@pytest.mark.asyncio
async def test_activate_subscription_server_not_found_raises(
    db_session: AsyncSession,
) -> None:
    fake_subscription = SimpleNamespace(id=1, server_id=999999)
    subs_repo = MagicMock()
    subs_repo.get_by_id = AsyncMock(return_value=fake_subscription)
    servers_repo = MagicMock()
    servers_repo.get_by_id = AsyncMock(return_value=None)

    with (
        patch("services.marzban_subscription.SubscriptionRepo", return_value=subs_repo),
        patch("services.marzban_subscription.ServerRepo", return_value=servers_repo),
    ):
        service = SubscriptionMarzbanService(session=db_session)
        with pytest.raises(ValueError, match="Server 999999 not found"):
            await service.activate_subscription(1)


# ---------------------------------------------------------------------------
# sync_traffic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_traffic_not_found_raises(db_session: AsyncSession) -> None:
    service = SubscriptionMarzbanService(session=db_session)

    with pytest.raises(ValueError, match="Subscription 999999 not found"):
        await service.sync_traffic(999999)


@pytest.mark.asyncio
async def test_sync_traffic_updates_db_and_calls_client(
    db_session: AsyncSession,
) -> None:
    """
    sync_traffic читает used_traffic из Marzban (get_user) и пишет
    его в БД — направление синхронизации только "из Marzban", без
    обратной записи (такого API-метода у Marzban нет вообще).
    """
    subscription = await _make_subscription(db_session, suffix="traffic1")
    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.get_user = AsyncMock(
        return_value=MarzbanUserInfo(
            username=subscription.marzban_username,
            enabled=True,
            data_limit_bytes=1000,
            data_used_bytes=500,
            expiry_timestamp=None,
        )
    )
    service._client = fake_client

    result = await service.sync_traffic(subscription.id)

    assert result.data_used_bytes == 500
    fake_client.get_user.assert_awaited_once_with(subscription.marzban_username)


# ---------------------------------------------------------------------------
# get_config_link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_link_not_found_raises(db_session: AsyncSession) -> None:
    service = SubscriptionMarzbanService(session=db_session)

    with pytest.raises(ValueError, match="Subscription 999999 not found"):
        await service.get_config_link(999999)


@pytest.mark.asyncio
async def test_get_config_link_returns_primary_link(db_session: AsyncSession) -> None:
    subscription = await _make_subscription(db_session, suffix="cfglink1")
    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.get_user = AsyncMock(
        return_value=MarzbanUserInfo(
            username=subscription.marzban_username,
            enabled=True,
            data_limit_bytes=1000,
            data_used_bytes=0,
            expiry_timestamp=None,
            config_links=["https://config.example/1"],
        )
    )
    fake_client.get_primary_config_link = Mock(return_value="https://config.example/1")
    service._client = fake_client

    result = await service.get_config_link(subscription.id)

    assert result == "https://config.example/1"
    fake_client.get_user.assert_awaited_once_with(subscription.marzban_username)


@pytest.mark.asyncio
async def test_get_config_link_no_links_returns_none(db_session: AsyncSession) -> None:
    subscription = await _make_subscription(db_session, suffix="cfglink2")
    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.get_user = AsyncMock(
        return_value=MarzbanUserInfo(
            username=subscription.marzban_username,
            enabled=True,
            data_limit_bytes=1000,
            data_used_bytes=0,
            expiry_timestamp=None,
            config_links=[],
        )
    )
    fake_client.get_primary_config_link = Mock(return_value=None)
    service._client = fake_client

    result = await service.get_config_link(subscription.id)

    assert result is None


# ---------------------------------------------------------------------------
# set_enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_enabled_not_found_raises(db_session: AsyncSession) -> None:
    service = SubscriptionMarzbanService(session=db_session)

    with pytest.raises(ValueError, match="Subscription 999999 not found"):
        await service.set_enabled(999999, enabled=True)


@pytest.mark.asyncio
async def test_set_enabled_true_activates(db_session: AsyncSession) -> None:
    subscription = await _make_subscription(db_session, suffix="enable1")
    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.update_user = AsyncMock()
    service._client = fake_client

    result = await service.set_enabled(subscription.id, enabled=True)

    assert result.status == SubscriptionStatus.ACTIVE
    assert result.disabled_reason is None
    fake_client.update_user.assert_awaited_once_with(
        subscription.marzban_username, enabled=True
    )


@pytest.mark.asyncio
async def test_set_enabled_false_disables_with_reason(
    db_session: AsyncSession,
) -> None:
    subscription = await _make_subscription(db_session, suffix="disable1")
    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.update_user = AsyncMock()
    service._client = fake_client

    result = await service.set_enabled(
        subscription.id, enabled=False, disabled_reason=DisabledReason.EXPIRED
    )

    assert result.status == SubscriptionStatus.DISABLED
    assert result.disabled_reason == DisabledReason.EXPIRED
    fake_client.update_user.assert_awaited_once_with(
        subscription.marzban_username, enabled=False
    )
