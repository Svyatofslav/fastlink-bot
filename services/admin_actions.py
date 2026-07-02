from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import AdminActionType, AdminEntityType
from database.repo.admin_actions import AdminActionRepo


class AdminActionLogService:
    """
    Сервис-аудитор для действий админов.

    Используется из хендлеров и application-сценариев,
    чтобы централизованно писать логи в AdminActionLog.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AdminActionRepo(session)

    async def log_action(
        self,
        *,
        admin_id: int,
        action: AdminActionType,
        entity_type: AdminEntityType,
        entity_id: int | None = None,
        payload_before: dict[str, Any] | None = None,
        payload_after: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> None:
        await self._repo.log(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type.value,
            entity_id=entity_id,
            payload_before=payload_before,
            payload_after=payload_after,
            comment=comment,
        )

    # Удобные шорткаты

    async def log_login(self, *, admin_id: int) -> None:
        await self.log_action(
            admin_id=admin_id,
            action=AdminActionType.LOGIN,
            entity_type=AdminEntityType.ADMIN,
            entity_id=admin_id,
        )

    async def log_logout(self, *, admin_id: int) -> None:
        await self.log_action(
            admin_id=admin_id,
            action=AdminActionType.LOGOUT,
            entity_type=AdminEntityType.ADMIN,
            entity_id=admin_id,
        )

    async def log_subscription_change(
        self,
        *,
        admin_id: int,
        subscription_id: int,
        action: AdminActionType,
        payload_before: dict[str, Any] | None = None,
        payload_after: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> None:
        await self.log_action(
            admin_id=admin_id,
            action=action,
            entity_type=AdminEntityType.SUBSCRIPTION,
            entity_id=subscription_id,
            payload_before=payload_before,
            payload_after=payload_after,
            comment=comment,
        )
