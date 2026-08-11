from __future__ import annotations

from collections.abc import Awaitable, Callable  # noqa: TC003
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from middlewares._common import extract_tg_user_id

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """
    Простое структурное логирование входящих событий.

    Логирует тип события, telegram_id, текст/данные, а также результат обработки.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user_id = extract_tg_user_id(event)
        payload: str | None = None
        event_type = type(event).__name__

        if isinstance(event, Message):
            payload = event.text or event.caption
        elif isinstance(event, CallbackQuery):
            payload = event.data

        logger.info(
            "update_received",
            event_type=event_type,
            telegram_id=tg_user_id,
            payload=payload,
        )

        try:
            result = await handler(event, data)
            logger.info(
                "update_processed",
                event_type=event_type,
                telegram_id=tg_user_id,
            )
            return result
        except Exception:
            logger.exception(
                "update_processing_error",
                event_type=event_type,
                telegram_id=tg_user_id,
            )
            raise
