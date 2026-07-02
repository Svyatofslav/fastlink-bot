from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from clients import get_marzban_client
from clients.marzban import MarzbanClient, MarzbanUserCreatePayload
from database.enums import SubscriptionStatus, DisabledReason
from database.models import Subscription
from database.repo.servers import ServerRepo
from database.repo.subscriptions import SubscriptionRepo


class SubscriptionMarzbanService:
    """
    Сервис для синхронизации подписок FastLink с Marzban.

    Используется из application-level use cases и scheduler'а.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._subscriptions = SubscriptionRepo(session)
        self._servers = ServerRepo(session)
        self._client: MarzbanClient = get_marzban_client()

    async def activate_subscription(self, subscription_id: int) -> Subscription:
        """
        Активировать подписку в FastLink и создать пользователя в Marzban.

        Поток:
        - Subscription найден в БД;
        - создаём пользователя в Marzban;
        - выставляем ACTIVE, subscription_url, сбрасываем disabled_reason.
        """
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        server_secrets = await self._servers.get_server_secrets(subscription.server_id)
        if server_secrets is None or not server_secrets.api_token:
            raise ValueError("Server API token is not configured")

        expires_at = subscription.expires_at or datetime.now(timezone.utc)
        expiry_ts = int(expires_at.timestamp())

        payload = MarzbanUserCreatePayload(
            username=subscription.marzban_username,
            inbound_tag=subscription.server.inbound_tag,
            data_limit_bytes=subscription.data_limit_bytes,
            expiry_timestamp=expiry_ts,
            enabled=True,
        )

        marzban_user = await self._client.create_user(
            payload,
            server_api_token=server_secrets.api_token,
        )

        subscription_url = self._client.build_subscription_url(marzban_user.username)

        subscription = await self._subscriptions.set_status(
            subscription,
            status=SubscriptionStatus.ACTIVE,
            subscription_url=subscription_url,
            disabled_reason=None,
        )

        return subscription

    async def sync_traffic(
        self,
        subscription_id: int,
        *,
        data_used_bytes: int,
    ) -> Subscription:
        """
        Обновить трафик по подписке в FastLink и в Marzban.
        """
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        server_secrets = await self._servers.get_server_secrets(subscription.server_id)
        if server_secrets is None or not server_secrets.api_token:
            raise ValueError("Server API token is not configured")

        subscription = await self._subscriptions.update_traffic(
            subscription,
            data_used_bytes=data_used_bytes,
        )

        await self._client.set_user_traffic(
            username=subscription.marzban_username,
            data_used_bytes=data_used_bytes,
            server_api_token=server_secrets.api_token,
        )

        return subscription

    async def set_enabled(
        self,
        subscription_id: int,
        *,
        enabled: bool,
        disabled_reason: DisabledReason | None = None,
    ) -> Subscription:
        """
        Включить/отключить подписку и пользователя в Marzban.

        enabled=False → DISABLED с disabled_reason.
        enabled=True  → ACTIVE без disabled_reason.
        """
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        server_secrets = await self._servers.get_server_secrets(subscription.server_id)
        if server_secrets is None or not server_secrets.api_token:
            raise ValueError("Server API token is not configured")

        await self._client.set_user_enabled(
            username=subscription.marzban_username,
            enabled=enabled,
            server_api_token=server_secrets.api_token,
        )

        if enabled:
            subscription = await self._subscriptions.set_status(
                subscription,
                status=SubscriptionStatus.ACTIVE,
                disabled_reason=None,
            )
        else:
            subscription = await self._subscriptions.set_status(
                subscription,
                status=SubscriptionStatus.DISABLED,
                disabled_reason=disabled_reason,
            )

        return subscription
