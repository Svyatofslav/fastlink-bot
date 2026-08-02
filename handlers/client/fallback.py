from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Router

from handlers.client.menu import render_main_menu
from utils.i18n import t

if TYPE_CHECKING:
    from aiogram.types import Message
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models import User

router = Router(name="client-fallback")


@router.message()
async def on_unrecognized_message(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    lang = user.language_code or "ru"
    await message.answer(t("common.unrecognized_message", lang))
    await render_main_menu(message, user, session)
