from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import SupportSenderType, SupportTicketCategory, SupportTicketStatus
from database.models import SupportMessage, SupportTicket
from database.repo.support import SupportMessageRepo, SupportTicketRepo

logger = structlog.get_logger(__name__)


class SupportService:
    """
    Оркестрация обращений в поддержку: создание тикета, добавление сообщений,
    назначение админа, смена статуса.
    Используется как основным ботом (создание тикета), так и ботом поддержки
    (ответы, назначение, закрытие).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tickets = SupportTicketRepo(session)
        self._messages = SupportMessageRepo(session)

    async def create_ticket(
        self,
        *,
        user_id: int,
        sender_telegram_id: int,
        text: str,
        category: SupportTicketCategory = SupportTicketCategory.GENERAL,
        subscription_id: int | None = None,
        payment_id: int | None = None,
        context_snapshot: dict[str, Any] | None = None,
    ) -> SupportTicket:
        ticket = await self._tickets.create(
            user_id=user_id,
            subscription_id=subscription_id,
            payment_id=payment_id,
            category=category,
            status=SupportTicketStatus.NEW,
            assigned_admin_id=None,
            context_snapshot=context_snapshot,
            resolved_at=None,
        )
        await self._messages.create(
            ticket_id=ticket.id,
            sender_type=SupportSenderType.USER,
            sender_telegram_id=sender_telegram_id,
            text=text,
        )
        logger.info(
            "support_ticket_created",
            ticket_id=ticket.id,
            user_id=user_id,
            category=category.value,
        )
        return ticket

    async def add_user_message(
        self, *, ticket_id: int, sender_telegram_id: int, text: str
    ) -> SupportMessage:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise ValueError(f"SupportTicket {ticket_id} not found")

        message = await self._messages.create(
            ticket_id=ticket_id,
            sender_type=SupportSenderType.USER,
            sender_telegram_id=sender_telegram_id,
            text=text,
        )
        # Если тикет уже был обработан/закрыт, но пользователь снова пишет —
        # возвращаем его в работу.
        if ticket.status in (SupportTicketStatus.RESOLVED, SupportTicketStatus.CLOSED):
            await self._tickets.set_status(
                ticket, status=SupportTicketStatus.IN_PROGRESS
            )
        return message

    async def add_admin_reply(
        self, *, ticket_id: int, admin_id: int, admin_telegram_id: int, text: str
    ) -> SupportMessage:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise ValueError(f"SupportTicket {ticket_id} not found")

        message = await self._messages.create(
            ticket_id=ticket_id,
            sender_type=SupportSenderType.ADMIN,
            sender_telegram_id=admin_telegram_id,
            text=text,
        )

        update_fields: dict[str, Any] = {}
        if ticket.status == SupportTicketStatus.NEW:
            update_fields["status"] = SupportTicketStatus.IN_PROGRESS
        if ticket.assigned_admin_id is None:
            update_fields["assigned_admin_id"] = admin_id
        if update_fields:
            await self._tickets.update(ticket, **update_fields)

        return message

    async def assign(self, *, ticket_id: int, admin_id: int) -> SupportTicket:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise ValueError(f"SupportTicket {ticket_id} not found")
        return await self._tickets.update(
            ticket,
            assigned_admin_id=admin_id,
            status=SupportTicketStatus.IN_PROGRESS
            if ticket.status == SupportTicketStatus.NEW
            else ticket.status,
        )

    async def close(self, *, ticket_id: int) -> SupportTicket:
        ticket = await self._tickets.get_by_id(ticket_id)
        if ticket is None:
            raise ValueError(f"SupportTicket {ticket_id} not found")
        return await self._tickets.update(
            ticket,
            status=SupportTicketStatus.CLOSED,
            resolved_at=datetime.now(timezone.utc),
        )

    async def get_open_ticket_for_user(self, user_id: int) -> SupportTicket | None:
        """Возвращает открытый тикет пользователя, если он есть (чтобы не плодить дубли)."""
        open_tickets = await self._tickets.get_open_by_user(user_id)
        return open_tickets[0] if open_tickets else None
