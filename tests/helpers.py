from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message


def make_callback(data: str, *, chat_id: int = 1, user_id: int = 1) -> CallbackQuery:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    callback.message = AsyncMock()
    callback.message.chat = MagicMock(id=chat_id)
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    return callback


def make_fsm_context(
    *, bot_id: int = 1, chat_id: int = 1, user_id: int = 1
) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=bot_id, chat_id=chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


def make_message(text: str, *, chat_id: int = 1, user_id: int = 1) -> Message:
    message = AsyncMock(spec=Message)
    message.text = text
    message.chat = MagicMock(id=chat_id)
    message.answer = AsyncMock()
    return message
