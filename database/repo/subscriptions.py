from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from database.enums import SubscriptionStatus
from database.models import Subscription
from database.repo.base import BaseRepo


class SubscriptionRepo(BaseRepo[Subscription]):
    model = Subscription

    async def get_active_by_user(self, user_id: int) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        return list(result.scalars().all())

    async def get_all_by_user(self, user_id: int) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_marzban_username(
        self, server_id: int, marzban_username: str
    ) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.server_id == server_id,
                Subscription.marzban_username == marzban_username,
            )
        )
        return result.scalar_one_or_none()

    async def get_expiring(self, within_days: int) -> list[Subscription]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at
                <= datetime.fromtimestamp(
                    now.timestamp() + within_days * 86400, tz=timezone.utc
                ),
                Subscription.expires_at > now,
            )
        )
        return list(result.scalars().all())

    async def get_expired(self) -> list[Subscription]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_high_usage(self, threshold_percent: int) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.data_limit_bytes > 0,
                (Subscription.data_used_bytes * 100 / Subscription.data_limit_bytes)
                >= threshold_percent,
            )
        )
        return list(result.scalars().all())

    async def update_traffic(
        self, subscription: Subscription, data_used_bytes: int
    ) -> Subscription:
        return await self.update(subscription, data_used_bytes=data_used_bytes)

    async def set_status(
        self,
        subscription: Subscription,
        status: SubscriptionStatus,
        **extra_fields,
    ) -> Subscription:
        return await self.update(subscription, status=status, **extra_fields)
