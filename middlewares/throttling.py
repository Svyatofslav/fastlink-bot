from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis


class ThrottlingMiddleware(BaseMiddleware):
    """
    Redis-based rate limiting — только для Message и CallbackQuery.
    По умолчанию: не более 1 события в 0.5 секунды на пользователя.
    Превышение — молча игнорируем (без ответа).

    Использует Redis из redis_url_rate_limit (DB3).
    Должен регистрироваться ПОСЛЕ UserMiddleware (нужен data["user"]).
    """

    def __init__(self, redis: Redis, rate_limit: float = 0.5) -> None:
        self.redis = redis
        self.rate_limit = rate_limit

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Throttle только message и callback, остальное пропускаем
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        user = data.get("user")
        if user is None:
            return await handler(event, data)

        key = f"throttle:{user.telegram_id}"
        is_throttled = await self.redis.get(key)

        if is_throttled:
            return None

        await self.redis.set(key, "1", px=int(self.rate_limit * 1000), nx=True)

        return await handler(event, data)
