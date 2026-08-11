from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from database.enums import AdminActionType, DisabledReason, SubscriptionStatus
from database.models import Subscription, Tariff, User  # noqa: TC001
from database.repo.subscriptions import SubscriptionRepo
from database.repo.tariffs import TariffRepo
from database.repo.users import UserRepo
from domain.subscription_extension import compute_extension
from services.admin_actions import AdminActionLogService
from services.marzban_subscription import SubscriptionMarzbanService
from services.notifications import NotificationService

TRAFFIC_THRESHOLD_80 = 80
TRAFFIC_THRESHOLD_95 = 95
TRAFFIC_THRESHOLD_100 = 100


def _subscription_snapshot(subscription: Subscription) -> dict[str, Any]:
    """
    Унифицированный snapshot подписки для аудита.
    """
    return {
        "id": subscription.id,
        "status": subscription.status.value,
        "disabled_reason": (
            subscription.disabled_reason.value
            if subscription.disabled_reason is not None
            else None
        ),
        "expires_at": (
            subscription.expires_at.isoformat()
            if subscription.expires_at is not None
            else None
        ),
        "data_limit_bytes": subscription.data_limit_bytes,
        "data_used_bytes": subscription.data_used_bytes,
    }


class SubscriptionService:
    """
    Application-уровневый сервис для работы с подписками FastLink.

    Оркестрирует:
    - создание подписки после успешного платежа,
    - активацию (Marzban + статус ACTIVE),
    - отключение/включение,
    - обновление трафика и уведомления по high usage.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._subscriptions = SubscriptionRepo(session)
        self._tariffs = TariffRepo(session)
        self._users = UserRepo(session)

        self._marzban = SubscriptionMarzbanService(session)
        self._notifications = NotificationService(session)
        self._admin_actions = AdminActionLogService(session)

    async def create_for_payment(
        self,
        *,
        user_id: int,
        tariff_id: int,
        server_id: int,
        marzban_username: str,
        starts_at: datetime | None,
        expires_at: datetime,
    ) -> Subscription:
        """
        Создать подписку в статусе PENDING на основе оплаченного тарифа и сервера.

        Предполагается вызов после SUCCEEDED платежа.
        """
        user: User | None = await self._users.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")

        tariff: Tariff | None = await self._tariffs.get_by_id(tariff_id)
        if tariff is None:
            raise ValueError(f"Tariff {tariff_id} not found")

        data_limit_bytes = tariff.data_limit_bytes

        return await self._subscriptions.create(
            user_id=user_id,
            server_id=server_id,
            tariff_id=tariff_id,
            marzban_username=marzban_username,
            status=SubscriptionStatus.PENDING,
            starts_at=starts_at,
            expires_at=expires_at,
            data_limit_bytes=data_limit_bytes,
            data_used_bytes=0,
            auto_renew=False,
            subscription_url="",
            disabled_reason=None,
        )

    async def activate(self, *, subscription_id: int) -> Subscription:
        """
        Активировать подписку: создать пользователя в Marzban и выставить статус ACTIVE.
        """
        return await self._marzban.activate_subscription(subscription_id)

    async def disable(
        self,
        *,
        subscription_id: int,
        disabled_reason: DisabledReason,
        admin_id: int | None = None,
    ) -> Subscription:
        """
        Отключить подписку и пользователя в Marzban с заданной причиной.
        """
        subscription = await self._marzban.set_enabled(
            subscription_id=subscription_id,
            enabled=False,
            disabled_reason=disabled_reason,
        )

        if admin_id is not None:
            await self._admin_actions.log_subscription_change(
                admin_id=admin_id,
                subscription_id=subscription_id,
                action=AdminActionType.DISABLE_SUBSCRIPTION,
                payload_before=None,
                payload_after=_subscription_snapshot(subscription),
                comment=f"Subscription disabled: {disabled_reason.value}",
            )

        return subscription

    async def enable(
        self,
        *,
        subscription_id: int,
        admin_id: int | None = None,
    ) -> Subscription:
        """
        Включить подписку и пользователя в Marzban.
        """
        subscription = await self._marzban.set_enabled(
            subscription_id=subscription_id,
            enabled=True,
            disabled_reason=None,
        )

        if admin_id is not None:
            await self._admin_actions.log_subscription_change(
                admin_id=admin_id,
                subscription_id=subscription_id,
                action=AdminActionType.ENABLE_SUBSCRIPTION,
                payload_before=None,
                payload_after=_subscription_snapshot(subscription),
                comment="Subscription enabled",
            )

        return subscription

    async def extend_for_payment(
        self,
        *,
        subscription_id: int,
        tariff_id: int,
    ) -> Subscription:
        """
        Продлевает существующую подписку после успешной оплаты продления.

        - expires_at сдвигается на tariff.duration_days от максимума
          (текущий expires_at, now) — чтобы не терять уже оплаченные
          дни при продлении заранее и не начислять их "в прошлое",
          если подписка уже истекла.
        - data_used_bytes сбрасывается в 0, data_limit_bytes берётся
          из тарифа (на случай если тариф с тех пор поменялся).
        - если подписка была DISABLED по причине EXPIRED, возвращаем
          её в ACTIVE через Marzban.
        """
        subscription = await self._subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        tariff = await self._tariffs.get_by_id(tariff_id)
        if tariff is None:
            raise ValueError(f"Tariff {tariff_id} not found")

        new_expires_at, new_data_limit_bytes = compute_extension(subscription, tariff)

        was_expired_disabled = (
            subscription.status == SubscriptionStatus.DISABLED
            and subscription.disabled_reason == DisabledReason.EXPIRED
        )

        subscription = await self._subscriptions.update(
            subscription,
            expires_at=new_expires_at,
            data_limit_bytes=new_data_limit_bytes,
        )

        if was_expired_disabled:
            subscription = await self._marzban.set_enabled(
                subscription_id=subscription.id,
                enabled=True,
                disabled_reason=None,
            )

        return subscription

    async def update_traffic_with_notifications(
        self,
        *,
        subscription_id: int,
        data_used_bytes: int,
    ) -> Subscription:
        """
        Обновить трафик по подписке и, при необходимости, инициировать уведомления
        о достижении порогов использования (80/95/100%).
        """
        subscription: Subscription | None = await self._subscriptions.get_by_id(
            subscription_id
        )
        if subscription is None:
            raise ValueError(f"Subscription {subscription_id} not found")

        subscription = await self._marzban.sync_traffic(
            subscription_id=subscription_id,
            data_used_bytes=data_used_bytes,
        )

        if subscription.data_limit_bytes <= 0:
            return subscription

        usage_percent = (
            subscription.data_used_bytes * 100 // subscription.data_limit_bytes
        )
        user_id = subscription.user_id

        if TRAFFIC_THRESHOLD_80 <= usage_percent < TRAFFIC_THRESHOLD_95:
            await self._notifications.notify_traffic_80(
                user_id=user_id,
                subscription_id=subscription.id,
            )
        elif TRAFFIC_THRESHOLD_95 <= usage_percent < TRAFFIC_THRESHOLD_100:
            await self._notifications.notify_traffic_95(
                user_id=user_id,
                subscription_id=subscription.id,
            )
        elif usage_percent >= TRAFFIC_THRESHOLD_100:
            await self._notifications.notify_traffic_100(
                user_id=user_id,
                subscription_id=subscription.id,
            )

        return subscription
