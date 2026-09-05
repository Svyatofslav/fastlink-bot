from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message


def extract_callback_id(data: str | None, prefix: str) -> int | None:
    """Извлекает числовой id из callback_data вида `{prefix}:{id}`."""
    if data is None or not data.startswith(f"{prefix}:"):
        return None

    raw_id = data.rsplit(":", 1)[-1]
    if not raw_id.isdigit():
        return None

    return int(raw_id)


def get_callback_message(callback: CallbackQuery) -> Message | None:
    """
    Безопасно достаёт редактируемое сообщение из callback.

    Возвращает None, если сообщения нет или оно недоступно для редактирования
    (InaccessibleMessage — Telegram возвращает такую заглушку для сообщений
    старше 48 часов или уже удалённых; у неё нет метода edit_text()).
    """
    message = callback.message
    if message is None or not hasattr(message, "edit_text"):
        return None
    return cast("Message", message)
