from __future__ import annotations

from dataclasses import dataclass

from database.models import Admin
from database.repo.admins import AdminRepo
from utils.password import hash_password, verify_password, needs_rehash


@dataclass(frozen=True)
class AdminCredentials:
    admin: Admin
    is_superadmin: bool


class AdminAuthService:
    def __init__(self, admin_repo: AdminRepo) -> None:
        self._admin_repo = admin_repo

    async def create_admin_with_plain_password(
        self,
        *,
        telegram_id: int,
        username: str | None,
        login: str,
        password_plain: str,
        secretword_plain: str,
        is_superadmin: bool = False,
        created_by_admin_id: int | None = None,
    ) -> Admin:
        password_hash = hash_password(password_plain)
        secretword_hash = hash_password(secretword_plain)

        return await self._admin_repo.create_admin(
            telegram_id=telegram_id,
            username=username,
            login=login,
            password_hash=password_hash,
            secretword_hash=secretword_hash,
            is_superadmin=is_superadmin,
            created_by_admin_id=created_by_admin_id,
        )

    async def verify_login(
        self,
        *,
        login: str,
        password_plain: str,
    ) -> AdminCredentials | None:
        """
        Проверить логин/пароль админа и при необходимости пересчитать хеш.

        Возвращает AdminCredentials или None, если логин/пароль неверны.
        """
        admin = await self._admin_repo.get_by_login(login)
        if admin is None or not admin.is_active:
            return None

        if not verify_password(password_plain, admin.password_hash):
            return None

        # При успешном логине можно сделать прозрачный rehash.
        if needs_rehash(admin.password_hash):
            new_hash = hash_password(password_plain)
            await self._admin_repo.update(admin, password_hash=new_hash)

        return AdminCredentials(admin=admin, is_superadmin=admin.is_superadmin)
