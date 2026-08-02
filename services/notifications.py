from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from database.enums import NotificationDeliveryStatus, NotificationType
from database.repo.notifications import NotificationRepo

logger = structlog.get_logger(__name__)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
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

    async def _try_notify(
        self,
        *,
        user_id: int,
        notification_type: NotificationType,
        subscription_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """
        Идемпотентная отправка одного уведомления заданного типа.

        Паттерн check-then-act (should_send -> log) уязвим к гонке при
        двух параллельных обработчиках одного события (например, два
        воркера одновременно обрабатывают один webhook). Оборачиваем
        INSERT в SAVEPOINT и ловим IntegrityError по
        uq_notifications_dedup (user_id, subscription_id, type) —
        второй параллельный вызов тихо получает False вместо падения
        и повторной отправки сообщения пользователю.
        """
        if not await self.should_send(
            user_id=user_id,
            notification_type=notification_type,
            subscription_id=subscription_id,
        ):
            return False

        try:
            async with self._session.begin_nested():
                await self._repo.log(
                    user_id=user_id,
                    notification_type=notification_type,
                    delivery_status=NotificationDeliveryStatus.SENT,
                    subscription_id=subscription_id,
                    payload=payload,
                )
        except IntegrityError:
            logger.info(
                "notification_dedup_race_detected",
                user_id=user_id,
                notification_type=notification_type.value,
                subscription_id=subscription_id,
            )
            return False

        return True

    async def notify_sub_expires_3d(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.SUB_EXPIRES_3D,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def notify_sub_expires_1d(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.SUB_EXPIRES_1D,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def notify_payment_succeeded(
        self,
        *,
        user_id: int,
        subscription_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.PAYMENT_SUCCEEDED,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def notify_donation_succeeded(
        self,
        *,
        user_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.DONATION_SUCCEEDED,
            payload=payload,
        )

    async def notify_refund_processed(
        self,
        *,
        user_id: int,
        subscription_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.REFUND_PROCESSED,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def notify_traffic_80(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_80,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def notify_traffic_95(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_95,
            subscription_id=subscription_id,
            payload=payload,
        )

    async def notify_traffic_100(
        self,
        *,
        user_id: int,
        subscription_id: int,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return await self._try_notify(
            user_id=user_id,
            notification_type=NotificationType.TRAFFIC_100,
            subscription_id=subscription_id,
            payload=payload,
        )
