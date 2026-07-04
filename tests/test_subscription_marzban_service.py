from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.marzban_subscription import SubscriptionMarzbanService
from clients.marzban import MarzbanClient, MarzbanUserInfo
from database.enums import SubscriptionStatus
from database.repo.subscriptions import SubscriptionRepo
from database.repo.servers import ServerRepo
from database.repo.tariffs import TariffRepo
from database.repo.users import UserRepo
from database.repo.dto import ServerSecrets


@pytest.mark.asyncio
async def test_activate_subscription_success(db_session: AsyncSession, monkeypatch):
    """
    Успешная активация: set ACTIVE и проставление subscription_url.
    """
    servers = ServerRepo(session=db_session)
    tariffs = TariffRepo(session=db_session)
    subs = SubscriptionRepo(session=db_session)
    users = UserRepo(session=db_session)

    # Создаём тестового пользователя, чтобы не ломать FK subscriptions.user_id
    user = await users.create(
        telegram_id=123456,
        username="testuser",
        first_name="Test",
        last_name="User",
        language_code="ru",
    )

    server = await servers.create(
        name="test-server",
        api_url="http://example.com/api",
        api_token="encrypted-api-token",
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

    fake_secrets = ServerSecrets(
        server_id=server.id,
        api_token="plain-api-token",
        metrics_token=None,
    )
    service._servers.get_server_secrets = AsyncMock(return_value=fake_secrets)

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
        api_url="http://example.com/api",
        api_token="encrypted-api-token-2",
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

    fake_secrets = ServerSecrets(
        server_id=server.id,
        api_token="plain-api-token-2",
        metrics_token=None,
    )
    service._servers.get_server_secrets = AsyncMock(return_value=fake_secrets)

    fake_client = AsyncMock(spec=MarzbanClient)
    fake_client.create_user = AsyncMock(side_effect=Exception("network error"))
    fake_client.build_subscription_url = Mock(
        return_value="https://fastlinkproject.com/sub/test-user-2"
    )
    service._client = fake_client

    with pytest.raises(Exception):
        await service.activate_subscription(subscription.id)
