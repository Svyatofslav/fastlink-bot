from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from database.repo import UserRepo

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession


class UserMiddleware(BaseMiddleware):
    """
    Получает или создаёт пользователя по telegram_id.
    Кладёт объект User в data["user"].
    Кладёт булев флаг data["user_created"] — True, если пользователь
    был создан именно в рамках текущего апдейта.
    Обновляет профиль если изменился.
    Блокирует забаненных — они не попадают в handlers.

    Должен регистрироваться ПОСЛЕ DbSessionMiddleware.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Безопасно достаём tg_user напрямую из event-объекта
        tg_user = None
        if isinstance(event, Message | CallbackQuery):
            tg_user = event.from_user

        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session: AsyncSession = data["session"]
        repo = UserRepo(session)

        user, created = await repo.get_or_create(tg_user)

        if not created:
            user = await repo.update_profile(user, tg_user)

        if user.is_banned:
            return None

        await repo.set_last_active(user)
        data["user"] = user
        data["user_created"] = created

        return await handler(event, data)
