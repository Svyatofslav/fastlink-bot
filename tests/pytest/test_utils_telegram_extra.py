from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

import utils.telegram as telegram_module
from utils.telegram import (
    disable_previous_menu,
    get_bot_username,
    get_support_bot_username,
    set_bot_username,
    set_support_bot_username,
)


@pytest.fixture(autouse=True)
def _reset_bot_identity():
    original = telegram_module._bot_identity
    telegram_module._bot_identity = telegram_module._BotIdentity()
    yield
    telegram_module._bot_identity = original


def test_get_bot_username_raises_when_not_initialized() -> None:
    with pytest.raises(RuntimeError, match="not initialized"):
        get_bot_username()


def test_set_and_get_bot_username_roundtrip() -> None:
    set_bot_username("fastlinkbot")
    assert get_bot_username() == "fastlinkbot"


def test_support_bot_username_defaults_to_none() -> None:
    assert get_support_bot_username() is None


def test_set_and_get_support_bot_username_roundtrip() -> None:
    set_support_bot_username("fastlinksupportbot")
    assert get_support_bot_username() == "fastlinksupportbot"


def test_set_support_bot_username_none_is_allowed() -> None:
    set_support_bot_username("something")
    set_support_bot_username(None)
    assert get_support_bot_username() is None


@pytest.mark.asyncio
async def test_disable_previous_menu_none_message_id_is_noop() -> None:
    bot = MagicMock()
    bot.edit_message_reply_markup = AsyncMock()

    await disable_previous_menu(bot, 123, None)

    bot.edit_message_reply_markup.assert_not_awaited()


@pytest.mark.asyncio
async def test_disable_previous_menu_calls_edit_when_message_id_present() -> None:
    bot = MagicMock()
    bot.edit_message_reply_markup = AsyncMock()

    await disable_previous_menu(bot, 123, 456)

    bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=123, message_id=456, reply_markup=None
    )


@pytest.mark.asyncio
async def test_disable_previous_menu_suppresses_telegram_bad_request() -> None:
    bot = MagicMock()
    bot.edit_message_reply_markup = AsyncMock(
        side_effect=TelegramBadRequest(MagicMock(), "message not found")
    )

    await disable_previous_menu(bot, 123, 456)  # не должно бросить исключение
