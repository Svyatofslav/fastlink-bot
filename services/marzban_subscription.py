from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from clients import get_marzban_client
from clients.marzban import MarzbanClient, MarzbanRequestError, MarzbanUserCreatePayload
from database.enums import DisabledReason, SubscriptionStatus
from database.models import Subscription  # noqa: TC001
from database.repo.servers import ServerRepo
from database.repo.subscriptions import SubscriptionRepo


class SubscriptionMarzbanService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._subscriptions = SubscriptionRepo(session)
        self._servers = ServerRepo(session)
        self._client: MarzbanClient = get_marzban_client()

    async def activate_subscription(self, subscription_id: int) -> Subscription:
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        server = await self._servers.get_by_id(subscription.server_id)
        if server is None:
            raise ValueError(f"Server {subscription.server_id} not found")

        expires_at = subscription.expires_at or datetime.now(UTC)
        expiry_ts = int(expires_at.timestamp())

        payload = MarzbanUserCreatePayload(
            username=subscription.marzban_username,
            inbound_tag=server.inbound_tag,
            data_limit_bytes=subscription.data_limit_bytes,
            expiry_timestamp=expiry_ts,
            enabled=True,
        )

        try:
            marzban_user = await self._client.create_user(payload)
        except MarzbanRequestError as exc:
            if exc.status_code == 409:
                marzban_user = await self._client.get_user(payload.username)
            else:
                raise

        subscription_url = self._client.build_subscription_url(marzban_user.username)

        return await self._subscriptions.set_status(
            subscription,
            status=SubscriptionStatus.ACTIVE,
            subscription_url=subscription_url,
            disabled_reason=None,
        )

    async def sync_traffic(
        self, subscription_id: int, *, data_used_bytes: int
    ) -> Subscription:
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        subscription = await self._subscriptions.update_traffic(
            subscription, data_used_bytes=data_used_bytes
        )

        await self._client.set_user_traffic(
            username=subscription.marzban_username,
            data_used_bytes=data_used_bytes,
        )
        return subscription

    async def get_config_link(self, subscription_id: int) -> str | None:
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        user_info = await self._client.get_user(subscription.marzban_username)
        return self._client.get_primary_config_link(user_info)

    async def set_enabled(
        self,
        subscription_id: int,
        *,
        enabled: bool,
        disabled_reason: DisabledReason | None = None,
    ) -> Subscription:
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        await self._client.set_user_enabled(
            username=subscription.marzban_username,
            enabled=enabled,
        )

        if enabled:
            subscription = await self._subscriptions.set_status(
                subscription, status=SubscriptionStatus.ACTIVE, disabled_reason=None
            )
        else:
            subscription = await self._subscriptions.set_status(
                subscription,
                status=SubscriptionStatus.DISABLED,
                disabled_reason=disabled_reason,
            )
        return subscription
