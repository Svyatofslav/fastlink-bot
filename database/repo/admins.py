from __future__ import annotations

from sqlalchemy import select

from database.models import Admin
from database.repo.base import BaseRepo


class AdminRepo(BaseRepo[Admin]):
    model = Admin

    async def get_by_telegram_id(self, telegram_id: int) -> Admin | None:
        result = await self.session.execute(
            select(Admin).where(Admin.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_login(self, login: str) -> Admin | None:
        result = await self.session.execute(select(Admin).where(Admin.login == login))
        return result.scalar_one_or_none()

    async def get_active_by_telegram_id(self, telegram_id: int) -> Admin | None:
        result = await self.session.execute(
            select(Admin).where(
                Admin.telegram_id == telegram_id,
                Admin.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def create_admin(
        self,
        *,
        telegram_id: int,
        username: str | None,
        login: str,
        password_hash: str,
        secretword_hash: str,
        is_superadmin: bool = False,
        created_by_admin_id: int | None = None,
    ) -> Admin:
        return await self.create(
            telegram_id=telegram_id,
            username=username,
            login=login,
            password_hash=password_hash,
            secretword_hash=secretword_hash,
            is_superadmin=is_superadmin,
            created_by_admin_id=created_by_admin_id,
        )

    async def set_active(self, admin: Admin, *, active: bool) -> Admin:
        return await self.update(admin, is_active=active)

    async def get_all_active(self) -> list[Admin]:
        result = await self.session.execute(
            select(Admin).where(Admin.is_active == True)  # noqa: E712
        )
        return list(result.scalars().all())
