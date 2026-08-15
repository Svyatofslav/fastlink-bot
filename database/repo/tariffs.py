from __future__ import annotations

from sqlalchemy import select

from database.models import Tariff
from database.repo.base import BaseRepo


class TariffRepo(BaseRepo[Tariff]):
    model = Tariff

    async def get_active(self) -> list[Tariff]:
        result = await self.session.execute(
            select(Tariff).where(Tariff.is_active == True).order_by(Tariff.sort_order)
        )
        return list(result.scalars().all())

    async def get_active_by_server(self, server_id: int) -> list[Tariff]:
        result = await self.session.execute(
            select(Tariff)
            .where(
                Tariff.is_active == True,
                (Tariff.server_id == server_id) | (Tariff.server_id == None),
            )
            .order_by(Tariff.sort_order)
        )
        return list(result.scalars().all())

    async def get_by_id_active(self, tariff_id: int) -> Tariff | None:
        result = await self.session.execute(
            select(Tariff).where(
                Tariff.id == tariff_id,
                Tariff.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def set_active(self, tariff: Tariff, *, active: bool) -> Tariff:
        return await self.update(tariff, is_active=active)
