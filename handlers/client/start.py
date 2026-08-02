from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import CommandStart

from handlers.client.menu import render_main_menu
from utils.i18n import t

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models import User

router = Router(name="client-start")


@router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    await state.clear()

    is_new_user = message.date is not None and (
        (
            message.date.replace(tzinfo=None) - user.created_at.replace(tzinfo=None)
        ).total_seconds()
        < 5
    )

    lang = user.language_code or "ru"
    key = "start.welcome.new" if is_new_user else "start.welcome.returning"
    text = t(key, lang)

    await message.answer(text)
    await render_main_menu(message, user, session)
