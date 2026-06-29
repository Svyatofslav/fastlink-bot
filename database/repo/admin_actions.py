from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from database.enums import AdminActionType
from database.models import AdminActionLog
from database.repo.base import BaseRepo


class AdminActionRepo(BaseRepo[AdminActionLog]):
    model = AdminActionLog

    async def log(
        self,
        admin_id: int,
        action: AdminActionType,
        entity_type: str,
        entity_id: int | None = None,
        payload_before: dict | None = None,
        payload_after: dict | None = None,
        comment: str | None = None,
    ) -> AdminActionLog:
        return await self.create(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_before=payload_before,
            payload_after=payload_after,
            comment=comment,
            created_at=datetime.now(timezone.utc),
        )

    async def get_by_admin(self, admin_id: int) -> list[AdminActionLog]:
        result = await self.session.execute(
            select(AdminActionLog)
            .where(AdminActionLog.admin_id == admin_id)
            .order_by(AdminActionLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_entity(
        self, entity_type: str, entity_id: int
    ) -> list[AdminActionLog]:
        result = await self.session.execute(
            select(AdminActionLog)
            .where(
                AdminActionLog.entity_type == entity_type,
                AdminActionLog.entity_id == entity_id,
            )
            .order_by(AdminActionLog.created_at.desc())
        )
        return list(result.scalars().all())
