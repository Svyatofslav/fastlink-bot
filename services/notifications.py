from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import NotificationDeliveryStatus, NotificationType
from database.repo.notifications import NotificationRepo


class NotificationService:
    """
    Доменный сервис для работы с уведомлениями:
    - дедупликация (was_sent / should_send),
    - логирование успешных/неуспешных отправок,
    - удобные методы под основные типы NotificationType.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = NotificationRepo(session)

    async def was_sent(
        self,
        *,
        user_id: int,
        notification_type: NotificationType,
        subscription_id: int | None = None,
    ) -> bool:
        return await self._repo.was_sent(
            user_id=user_id,
            notification_type=notification_type,
            subscription_id=subscription_id,
        )

    async def should_send(
        self,
        *,
        user_id: int,
        notification_type: NotificationType,
        subscription_id: int | None = None,
    ) -> bool:
        already_sent = await self.was_sent(
            user_id=user_id,
            notification_type=notification_type,
            subscription_id=subscription_id,
        )
        return not already_sent

    async def log_success(
        self,
        *,
        user_id: int,
        notification_type: NotificationType,
        subscription_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.log(
            user_id=user_id,
            notification_type=notification_type,
            delivery_status=NotificationDeliveryStatus.SENT,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def log_failure(
        self,
        *,
        user_id: int,
        notification_type: NotificationType,
        subscription_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.log(
            user_id=user_id,
            notification_type=notification_type,
            delivery_status=NotificationDeliveryStatus.FAILED,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def notify_sub_expires_3d(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.should_send(
            user_id=user_id,
            notification_type=NotificationType.SUB_EXPIRES_3D,
            subscription_id=subscription_id,
        ):
            return False

        await self.log_success(
            user_id=user_id,
            notification_type=NotificationType.SUB_EXPIRES_3D,
            subscription_id=subscription_id,
            payload=payload,
        )
        return True

    async def notify_sub_expires_1d(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.should_send(
            user_id=user_id,
            notification_type=NotificationType.SUB_EXPIRES_1D,
            subscription_id=subscription_id,
        ):
            return False

        await self.log_success(
            user_id=user_id,
            notification_type=NotificationType.SUB_EXPIRES_1D,
            subscription_id=subscription_id,
            payload=payload,
        )
        return True

    async def notify_payment_succeeded(
        self,
        *,
        user_id: int,
        subscription_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.should_send(
            user_id=user_id,
            notification_type=NotificationType.PAYMENT_SUCCEEDED,
            subscription_id=subscription_id,
        ):
            return False

        await self.log_success(
            user_id=user_id,
            notification_type=NotificationType.PAYMENT_SUCCEEDED,
            subscription_id=subscription_id,
            payload=payload,
        )
        return True

    async def notify_refund_processed(
        self,
        *,
        user_id: int,
        subscription_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.should_send(
            user_id=user_id,
            notification_type=NotificationType.REFUND_PROCESSED,
            subscription_id=subscription_id,
        ):
            return False

        await self.log_success(
            user_id=user_id,
            notification_type=NotificationType.REFUND_PROCESSED,
            subscription_id=subscription_id,
            payload=payload,
        )
        return True

    async def notify_traffic_80(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.should_send(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_80,
            subscription_id=subscription_id,
        ):
            return False

        await self.log_success(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_80,
            subscription_id=subscription_id,
            payload=payload,
        )
        return True

    async def notify_traffic_95(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.should_send(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_95,
            subscription_id=subscription_id,
        ):
            return False

        await self.log_success(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_95,
            subscription_id=subscription_id,
            payload=payload,
        )
        return True

    async def notify_traffic_100(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.should_send(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_100,
            subscription_id=subscription_id,
        ):
            return False

        await self.log_success(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_100,
            subscription_id=subscription_id,
            payload=payload,
        )
        return True
