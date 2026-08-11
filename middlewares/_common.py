from __future__ import annotations

from aiogram.types import CallbackQuery, Message, TelegramObject


def extract_tg_user_id(event: TelegramObject) -> int | None:
    """Достаёт telegram_id отправителя из Message/CallbackQuery, если есть."""
    if isinstance(event, Message | CallbackQuery) and event.from_user:
        return event.from_user.id
    return None
