from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware

from middlewares._common import extract_tg_user_id
from services import AdminSessionStore

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import TelegramObject
    from redis.asyncio import Redis

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

        tg_user_id = extract_tg_user_id(event)

        if tg_user_id is None:
            return await handler(event, data)

        session = await self._store.get_session(tg_user_id)
        if session is not None:
            data["admin_session"] = session

        return await handler(event, data)
