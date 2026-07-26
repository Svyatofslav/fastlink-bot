from __future__ import annotations

from sqlalchemy import select

from database.enums import SupportTicketStatus
from database.models import SupportMessage, SupportTicket
from database.repo.base import BaseRepo


class SupportTicketRepo(BaseRepo[SupportTicket]):
    model = SupportTicket

    async def get_by_user(self, user_id: int) -> list[SupportTicket]:
        result = await self.session.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_open_by_user(self, user_id: int) -> list[SupportTicket]:
        result = await self.session.execute(
            select(SupportTicket).where(
                SupportTicket.user_id == user_id,
                SupportTicket.status.in_(
                    (SupportTicketStatus.NEW, SupportTicketStatus.IN_PROGRESS)
                ),
            )
        )
        return list(result.scalars().all())

    async def get_unassigned(self) -> list[SupportTicket]:
        result = await self.session.execute(
            select(SupportTicket)
            .where(
                SupportTicket.status == SupportTicketStatus.NEW,
                SupportTicket.assigned_admin_id.is_(None),
            )
            .order_by(SupportTicket.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_admin(self, admin_id: int) -> list[SupportTicket]:
        result = await self.session.execute(
            select(SupportTicket)
            .where(SupportTicket.assigned_admin_id == admin_id)
            .order_by(SupportTicket.created_at.desc())
        )
        return list(result.scalars().all())

    async def set_status(
        self, ticket: SupportTicket, *, status: SupportTicketStatus, **extra
    ) -> SupportTicket:
        return await self.update(ticket, status=status, **extra)


class SupportMessageRepo(BaseRepo[SupportMessage]):
    model = SupportMessage

    async def get_by_ticket(self, ticket_id: int) -> list[SupportMessage]:
        result = await self.session.execute(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == ticket_id)
            .order_by(SupportMessage.created_at.asc())
        )
        return list(result.scalars().all())
