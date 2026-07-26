from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import settings
from database.models import User
from keyboards.client import CB_MENU_HELP, back_to_main_kb, support_kb
from utils.i18n import t

router = Router(name="client-support")


@router.callback_query(lambda c: c.data == CB_MENU_HELP)
async def on_help(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    """
    Кнопка "Помощь": показывает ссылку на бот поддержки.
    Управляется флагом FEATURE_SUPPORT_ENABLED — можно быстро
    отключить обращения в поддержку (например, на время техработ)
    без редеплоя кода.
    Полноценная логика тикетов появится после запуска support_bot.py.
    """
    await state.clear()
    lang = user.language_code or "ru"

    if not settings.feature_support_enabled or not settings.support_bot_username:
        text = t("support.unavailable", lang)
        await callback.message.edit_text(text, reply_markup=back_to_main_kb(user))
        await callback.answer()
        return

    text = t("support.intro_text", lang)
    await callback.message.edit_text(text, reply_markup=support_kb(user))
    await callback.answer()
