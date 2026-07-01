from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

from services import AdminSessionStore
from settings_schema import Settings


class AdminSessionMiddleware(BaseMiddleware):
    """
    Middleware для admin-сессий.

    Если у текущего telegram_id есть активная admin-сессия в Redis,
    кладёт её в data["admin_session"].
    """

    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._store = AdminSessionStore(redis=redis, settings=settings)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user_id: int | None = None

        if isinstance(event, Message) and event.from_user:
            tg_user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            tg_user_id = event.from_user.id

        if tg_user_id is None:
            return await handler(event, data)

        session = await self._store.get_session(tg_user_id)
        if session is not None:
            data["admin_session"] = session

        return await handler(event, data)
