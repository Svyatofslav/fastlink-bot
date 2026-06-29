from __future__ import annotations

from sqlalchemy import select

from database.models import Server
from database.repo.base import BaseRepo


class ServerRepo(BaseRepo[Server]):
    model = Server

    async def get_active(self) -> list[Server]:
        result = await self.session.execute(
            select(Server)
            .where(Server.is_active == True)  # noqa: E712
            .order_by(Server.sort_order)
        )
        return list(result.scalars().all())

    async def get_by_id_active(self, server_id: int) -> Server | None:
        result = await self.session.execute(
            select(Server).where(
                Server.id == server_id,
                Server.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def set_active(self, server: Server, *, active: bool) -> Server:
        return await self.update(server, is_active=active)
