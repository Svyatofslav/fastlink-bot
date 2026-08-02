from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from database.repo.users import UserRepo
from keyboards.client import (
    CB_MENU_LANGUAGE,
    CB_MENU_MAIN,
    main_menu_kb,
)
from utils.i18n import t
from utils.telegram import disable_previous_menu

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models import User

router = Router(name="client-menu")


async def render_main_menu(
    message: Message,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Общий рендер главного меню.
    Используется из /start и после отправки ссылок/QR подписки.

    Гасит клавиатуру предыдущего активного "экрана" (last_active_message_id)
    перед отправкой нового сообщения, затем сохраняет id нового сообщения
    как текущий активный экран.
    """
    lang = user.language_code or "ru"
    text = t("main.menu.title", lang)

    bot = message.bot
    if bot is not None:
        await disable_previous_menu(
            bot,
            message.chat.id,
            user.last_active_message_id,
        )

    sent = await message.answer(text, reply_markup=main_menu_kb(user))
    await UserRepo(session).set_last_active_message_id(user, sent.message_id)


@router.callback_query(lambda c: c.data == CB_MENU_MAIN)
async def on_back_to_main(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    """
    Обработчик кнопки "🏠 Главное меню".
    Сбрасывает любое текущее FSM-состояние и возвращает пользователя
    в главное меню.
    """
    await state.clear()

    message = callback.message
    if message is None or not isinstance(message, Message):
        await callback.answer()
        return

    lang = user.language_code or "ru"
    text = t("main.menu.title", lang)
    await message.edit_text(text, reply_markup=main_menu_kb(user))
    await callback.answer()


@router.callback_query(lambda c: c.data == CB_MENU_LANGUAGE)
async def on_change_language(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    """
    Обработчик кнопки "🌐 Язык".
    Переключает язык между ru и en и перерисовывает главное меню.
    """
    await state.clear()

    message = callback.message
    if message is None or not isinstance(message, Message):
        await callback.answer()
        return

    users_repo = UserRepo(session)
    current_lang = (user.language_code or "ru").lower()
    new_lang = "en" if current_lang == "ru" else "ru"

    user = await users_repo.update(user, language_code=new_lang)

    text = t("main.menu.title", new_lang)
    await message.edit_text(text, reply_markup=main_menu_kb(user))
    await callback.answer()
