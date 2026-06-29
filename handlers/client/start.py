from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="client-start")


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "FastLink bot is running.\n"
        "Базовый pipeline работает: update -> middleware -> handler -> response."
    )
