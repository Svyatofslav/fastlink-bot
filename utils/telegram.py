from __future__ import annotations

from contextlib import suppress

from aiogram import Bot  # noqa: TC002
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
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )


class _BotIdentity:
    """Контейнер для username ботов — резолвится один раз при старте приложения."""

    main_username: str | None = None
    support_username: str | None = None


_bot_identity = _BotIdentity()


def set_bot_username(username: str) -> None:
    """
    Сохраняет username основного бота, полученный через bot.get_me() при
    старте приложения (bot.py). Вызывается один раз до начала обработки апдейтов.
    """
    _bot_identity.main_username = username


def get_bot_username() -> str:
    """
    Возвращает username основного бота, ранее сохранённый через set_bot_username().

    Вызывается из PaymentService для построения return_url YooKassa.
    Если username не инициализирован — это ошибка порядка запуска
    (set_bot_username() должен быть вызван в build_bot_and_dispatcher()
    до создания Dispatcher/начала polling/webhook), а не штатная ситуация.
    """
    if _bot_identity.main_username is None:
        raise RuntimeError(
            "Bot username is not initialized. "
            "Call set_bot_username() during startup (after bot.get_me()) "
            "before constructing PaymentService."
        )
    return _bot_identity.main_username


def set_support_bot_username(username: str | None) -> None:
    """
    Сохраняет username бота поддержки, полученный через best-effort
    bot.get_me() при старте основного бота (bot.py).

    В отличие от set_bot_username(), это опционально: SUPPORT_BOT_TOKEN может
    быть пустым или невалидным — в обоих случаях сюда придёт None, и
    get_support_bot_username() вернёт None, а не бросит исключение
    (поддержку легитимно можно отключить флагом FEATURE_SUPPORT_ENABLED
    без редеплоя, и это не ошибка конфигурации).
    """
    _bot_identity.support_username = username


def get_support_bot_username() -> str | None:
    """
    Возвращает username бота поддержки, если он был успешно резолвлен при
    старте, иначе None — вызывающий код обязан показать "поддержка
    недоступна" (см. handlers/client/support.py), а не считать это ошибкой.
    """
    return _bot_identity.support_username
