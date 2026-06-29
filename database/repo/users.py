from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import User as TelegramUser
from sqlalchemy import select

from database.models import User
from database.repo.base import BaseRepo


class UserRepo(BaseRepo[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, tg_user: TelegramUser) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(tg_user.id)
        if user is not None:
            return user, False

        user = await self.create(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code or "ru",
        )
        return user, True

    async def update_profile(self, user: User, tg_user: TelegramUser) -> User:
        changed: dict = {}
        if user.username != tg_user.username:
            changed["username"] = tg_user.username
        if user.first_name != tg_user.first_name:
            changed["first_name"] = tg_user.first_name
        if user.last_name != tg_user.last_name:
            changed["last_name"] = tg_user.last_name
        if changed:
            return await self.update(user, **changed)
        return user

    async def set_last_active(self, user: User) -> None:
        await self.update(user, last_active_at=datetime.now(timezone.utc))

    async def set_banned(self, user: User, *, banned: bool) -> User:
        return await self.update(user, is_banned=banned)

    async def get_all_active(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.is_active == True, User.is_banned == False)  # noqa: E712
        )
        return list(result.scalars().all())
