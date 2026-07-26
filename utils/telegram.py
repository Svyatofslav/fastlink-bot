from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest


async def disable_previous_menu(bot: Bot, chat_id: int, message_id: int | None) -> None:
    """
    Гасит inline-клавиатуру у предыдущего "живого" экрана.

    Вызывается перед отправкой НОВОГО сообщения с кнопками (не перед edit_text —
    там message_id не меняется, и это не нужно).
    TelegramBadRequest ловим молча: сообщение может быть уже удалено,
    слишком старым (>48ч) или уже без клавиатуры — это не ошибка сценария.
    """
    if message_id is None:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None
        )
    except TelegramBadRequest:
        pass
