from __future__ import annotations

from collections.abc import Awaitable, Callable  # noqa: TC003
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject  # noqa: TC002
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: TC002


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
