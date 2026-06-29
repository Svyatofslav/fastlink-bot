from __future__ import annotations

from sqlalchemy import select

from database.enums import PaymentStatus
from database.models import Payment
from database.repo.base import BaseRepo


class PaymentRepo(BaseRepo[Payment]):
    model = Payment

    async def get_by_idempotence_key(self, key: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.idempotence_key == key)
        )
        return result.scalar_one_or_none()

    async def get_by_provider_payment_id(
        self, provider_payment_id: str
    ) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        )
        return result.scalar_one_or_none()

    async def get_all_by_user(self, user_id: int) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_subscription(self, subscription_id: int) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.subscription_id == subscription_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def set_status(
        self,
        payment: Payment,
        status: PaymentStatus,
        **extra_fields,
    ) -> Payment:
        return await self.update(payment, status=status, **extra_fields)
