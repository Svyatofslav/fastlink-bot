# database/repo/refunds.py

from __future__ import annotations

from sqlalchemy import select

from database.enums import RefundStatus
from database.models import Refund
from database.repo.base import BaseRepo


class RefundRepo(BaseRepo[Refund]):
    model = Refund

    async def get_by_payment(self, payment_id: int) -> list[Refund]:
        result = await self.session.execute(
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_refund_request(self, refund_request_id: int) -> list[Refund]:
        result = await self.session.execute(
            select(Refund)
            .where(Refund.refund_request_id == refund_request_id)
            .order_by(Refund.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_provider_refund_id(
        self,
        provider_refund_id: str,
    ) -> Refund | None:
        result = await self.session.execute(
            select(Refund).where(Refund.provider_refund_id == provider_refund_id)
        )
        return result.scalar_one_or_none()

    async def set_status(
        self,
        refund: Refund,
        status: RefundStatus,
        **extra_fields,
    ) -> Refund:
        return await self.update(refund, status=status, **extra_fields)
