from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.models import User
from database.repo.base import BaseRepo

if TYPE_CHECKING:
    from aiogram.types import User as TelegramUser


class UserRepo(BaseRepo[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, tg_user: TelegramUser) -> tuple[User, bool]:
        """
        Идемпотентно по telegram_id: при гонке двух одновременных /start
        от одного и того же пользователя ловим IntegrityError на unique
        constraint users.telegram_id и возвращаем уже созданную запись
        вместо падения наружу.
        """
        user = await self.get_by_telegram_id(tg_user.id)
        if user is not None:
            return user, False

        try:
            async with self.session.begin_nested():
                user = await self.create(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                    language_code=tg_user.language_code or "ru",
                )
        except IntegrityError:
            user = await self.get_by_telegram_id(tg_user.id)
            if user is None:
                raise
            return user, False

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
        await self.update(user, last_active_at=datetime.now(UTC))

    async def set_banned(self, user: User, *, banned: bool) -> User:
        return await self.update(user, is_banned=banned)

    async def get_all_active(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.is_active == True, User.is_banned == False)  # noqa: E712
        )
        return list(result.scalars().all())

    # database/repo/users.py — добавить метод в класс UserRepo
    async def set_last_active_message_id(
        self, user: User, message_id: int | None
    ) -> User:
        return await self.update(user, last_active_message_id=message_id)
