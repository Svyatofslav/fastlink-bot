from __future__ import annotations

from sqlalchemy import select

from database.enums import NotificationDeliveryStatus, NotificationType
from database.models import NotificationLog
from database.repo.base import BaseRepo


class NotificationRepo(BaseRepo[NotificationLog]):
    model = NotificationLog

    async def was_sent(
        self,
        user_id: int,
        notification_type: NotificationType,
        subscription_id: int | None = None,
    ) -> bool:
        query = select(NotificationLog).where(
            NotificationLog.user_id == user_id,
            NotificationLog.type == notification_type,
        )
        if subscription_id is not None:
            query = query.where(NotificationLog.subscription_id == subscription_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def log(
        self,
        user_id: int,
        notification_type: NotificationType,
        delivery_status: NotificationDeliveryStatus,
        subscription_id: int | None = None,
        payload: dict | None = None,
    ) -> NotificationLog:
        from datetime import datetime, timezone

        return await self.create(
            user_id=user_id,
            subscription_id=subscription_id,
            type=notification_type,
            delivery_status=delivery_status,
            payload=payload,
            sent_at=datetime.now(timezone.utc),
        )

    async def get_by_user(self, user_id: int) -> list[NotificationLog]:
        result = await self.session.execute(
            select(NotificationLog)
            .where(NotificationLog.user_id == user_id)
            .order_by(NotificationLog.sent_at.desc())
        )
        return list(result.scalars().all())
