# database/repo/refund_requests.py

from __future__ import annotations

from sqlalchemy import select

from database.enums import RefundRequestStatus
from database.models import RefundRequest
from database.repo.base import BaseRepo


class RefundRequestRepo(BaseRepo[RefundRequest]):
    model = RefundRequest

    async def get_by_subscription(self, subscription_id: int) -> list[RefundRequest]:
        result = await self.session.execute(
            select(RefundRequest)
            .where(RefundRequest.subscription_id == subscription_id)
            .order_by(RefundRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_user(self, user_id: int) -> list[RefundRequest]:
        result = await self.session.execute(
            select(RefundRequest)
            .where(RefundRequest.user_id == user_id)
            .order_by(RefundRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending(self) -> list[RefundRequest]:
        result = await self.session.execute(
            select(RefundRequest).where(
                RefundRequest.status == RefundRequestStatus.NEW,
            )
        )
        return list(result.scalars().all())

    async def set_status(
        self,
        refund_request: RefundRequest,
        status: RefundRequestStatus,
        **extra_fields,
    ) -> RefundRequest:
        return await self.update(refund_request, status=status, **extra_fields)
