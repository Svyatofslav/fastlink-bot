from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from clients.marzban import MarzbanClient, MarzbanRequestError, MarzbanUserInfo
from database.enums import SubscriptionStatus
from database.repo.servers import ServerRepo
from database.repo.subscriptions import SubscriptionRepo
from database.repo.tariffs import TariffRepo
from database.repo.users import UserRepo
from services.marzban_subscription import SubscriptionMarzbanService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_activate_subscription_success(db_session: AsyncSession, monkeypatch):
    """
    Успешная активация: set ACTIVE и проставление subscription_url.
    """
    servers = ServerRepo(session=db_session)
    tariffs = TariffRepo(session=db_session)
    subs = SubscriptionRepo(session=db_session)
    users = UserRepo(session=db_session)

    user = await users.create(
        telegram_id=123456,
        username="testuser",
        first_name="Test",
        last_name="User",
        language_code="ru",
    )

    server = await servers.create(
        name="test-server",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="test-inbound",
        sort_order=100,
        is_active=True,
    )
    tariff = await tariffs.create(
        server_id=server.id,
        name="test-tariff",
        duration_days=30,
        data_limit_bytes=1000,
        price_amount=100,
    )
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="test-user",
        status=SubscriptionStatus.PENDING,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="initial-url",
        disabled_reason=None,
    )
    await db_session.commit()

    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.create_user = AsyncMock(
        return_value=MarzbanUserInfo(
            username="test-user",
            enabled=True,
            data_limit_bytes=1000,
            data_used_bytes=0,
            expiry_timestamp=None,
        )
    )
    fake_client.build_subscription_url = Mock(
        return_value="https://fastlinkproject.com/sub/test-user"
    )
    service._client = fake_client

    result = await service.activate_subscription(subscription.id)

    assert result.status == SubscriptionStatus.ACTIVE
    assert result.subscription_url == "https://fastlinkproject.com/sub/test-user"


@pytest.mark.asyncio
async def test_activate_subscription_network_error(
    db_session: AsyncSession, monkeypatch
):
    """
    При ошибке клиента исключение пробрасывается вверх (минимальный кейс).
    """
    servers = ServerRepo(session=db_session)
    tariffs = TariffRepo(session=db_session)
    subs = SubscriptionRepo(session=db_session)
    users = UserRepo(session=db_session)

    user = await users.create(
        telegram_id=234567,
        username="testuser2",
        first_name="Test2",
        last_name="User2",
        language_code="ru",
    )

    server = await servers.create(
        name="test-server-2",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="test-inbound",
        sort_order=100,
        is_active=True,
    )
    tariff = await tariffs.create(
        server_id=server.id,
        name="test-tariff-2",
        duration_days=30,
        data_limit_bytes=1000,
        price_amount=100,
    )
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="test-user-2",
        status=SubscriptionStatus.PENDING,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="initial-url-2",
        disabled_reason=None,
    )
    await db_session.commit()

    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.create_user = AsyncMock(
        side_effect=MarzbanRequestError("network error")
    )
    fake_client.build_subscription_url = Mock(
        return_value="https://fastlinkproject.com/sub/test-user-2"
    )
    service._client = fake_client

    with pytest.raises(MarzbanRequestError):
        await service.activate_subscription(subscription.id)


@pytest.mark.asyncio
async def test_activate_subscription_conflict_recovers_existing_user(
    db_session: AsyncSession, monkeypatch
):
    """
    Если Marzban отвечает 409 "user already exists" (например, повторный
    вызов activate_subscription для username, который уже был создан
    ранее — не через штатную webhook-цепочку, где гонка закрыта на уровне
    FOR UPDATE SKIP LOCKED), сервис не должен падать, а должен забрать
    уже существующего пользователя через get_user и продолжить активацию.
    """
    servers = ServerRepo(session=db_session)
    tariffs = TariffRepo(session=db_session)
    subs = SubscriptionRepo(session=db_session)
    users = UserRepo(session=db_session)

    user = await users.create(
        telegram_id=654321,
        username="conflictuser",
        first_name="Test",
        last_name="User",
        language_code="ru",
    )

    server = await servers.create(
        name="test-server-conflict",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="test-inbound",
        sort_order=100,
        is_active=True,
    )
    tariff = await tariffs.create(
        server_id=server.id,
        name="test-tariff-conflict",
        duration_days=30,
        data_limit_bytes=1000,
        price_amount=100,
    )
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="conflict-user",
        status=SubscriptionStatus.PENDING,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="initial-url",
        disabled_reason=None,
    )
    await db_session.commit()

    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.create_user = AsyncMock(
        side_effect=MarzbanRequestError(
            "Marzban client error: status=409, body=User already exists",
            status_code=409,
        )
    )
    fake_client.get_user = AsyncMock(
        return_value=MarzbanUserInfo(
            username="conflict-user",
            enabled=True,
            data_limit_bytes=1000,
            data_used_bytes=0,
            expiry_timestamp=None,
        )
    )
    fake_client.build_subscription_url = Mock(
        return_value="https://fastlinkproject.com/sub/conflict-user"
    )
    service._client = fake_client

    result = await service.activate_subscription(subscription.id)

    fake_client.create_user.assert_awaited_once()
    fake_client.get_user.assert_awaited_once_with("conflict-user")
    assert result.status == SubscriptionStatus.ACTIVE
    assert result.subscription_url == "https://fastlinkproject.com/sub/conflict-user"


@pytest.mark.asyncio
async def test_activate_subscription_non_conflict_error_propagates(
    db_session: AsyncSession, monkeypatch
):
    """
    Любая другая ошибка Marzban (не 409) должна пробрасываться наружу,
    а не тихо поглощаться — иначе мы замаскируем реальный сбой (например,
    500 от Marzban) под успешную активацию.
    """
    servers = ServerRepo(session=db_session)
    tariffs = TariffRepo(session=db_session)
    subs = SubscriptionRepo(session=db_session)
    users = UserRepo(session=db_session)

    user = await users.create(
        telegram_id=654322,
        username="failuser",
        first_name="Test",
        last_name="User",
        language_code="ru",
    )
    server = await servers.create(
        name="test-server-fail",
        country_code=None,
        country_name=None,
        emoji=None,
        marzban_node_id=1,
        metrics_url=None,
        metrics_token=None,
        inbound_tag="test-inbound",
        sort_order=100,
        is_active=True,
    )
    tariff = await tariffs.create(
        server_id=server.id,
        name="test-tariff-fail",
        duration_days=30,
        data_limit_bytes=1000,
        price_amount=100,
    )
    subscription = await subs.create(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username="fail-user",
        status=SubscriptionStatus.PENDING,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url="initial-url",
        disabled_reason=None,
    )
    await db_session.commit()

    service = SubscriptionMarzbanService(session=db_session)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.create_user = AsyncMock(
        side_effect=MarzbanRequestError(
            "Marzban server error: status=500, body=Internal Server Error",
            status_code=500,
        )
    )
    service._client = fake_client

    with pytest.raises(MarzbanRequestError):
        await service.activate_subscription(subscription.id)

    fake_client.get_user.assert_not_called()
