from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from handlers.client.menu import on_back_to_main, on_change_language, render_main_menu
from keyboards.client import CB_MENU_LANGUAGE, CB_MENU_MAIN
from tests.pytest.factories import make_user
from tests.pytest.helpers import make_fsm_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def make_message_callback(data: str, *, chat_id: int = 1, has_bot: bool = True):
    callback = AsyncMock()
    callback.data = data
    callback.answer = AsyncMock()
    message = AsyncMock(spec=Message)
    message.chat = MagicMock(id=chat_id)
    message.edit_text = AsyncMock()
    message.bot = MagicMock() if has_bot else None
    callback.message = message
    return callback


# ---------------------------------------------------------------------------
# render_main_menu
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_main_menu_with_bot_disables_previous_and_saves_message_id() -> (
    None
):
    user = make_user(last_active_message_id=555)
    message = MagicMock()
    message.bot = MagicMock()
    message.chat = MagicMock(id=42)
    sent = MagicMock(message_id=777)
    message.answer = AsyncMock(return_value=sent)

    users_repo = MagicMock()
    users_repo.set_last_active_message_id = AsyncMock()

    with (
        patch(
            "handlers.client.menu.disable_previous_menu", new=AsyncMock()
        ) as disable_mock,
        patch("handlers.client.menu.UserRepo", return_value=users_repo),
    ):
        await render_main_menu(message, user, MagicMock())

    disable_mock.assert_awaited_once_with(message.bot, 42, 555)
    message.answer.assert_awaited_once()
    users_repo.set_last_active_message_id.assert_awaited_once_with(user, 777)


@pytest.mark.asyncio
async def test_render_main_menu_without_bot_skips_disable_previous() -> None:
    user = make_user(last_active_message_id=None)
    message = MagicMock()
    message.bot = None
    message.chat = MagicMock(id=42)
    sent = MagicMock(message_id=888)
    message.answer = AsyncMock(return_value=sent)

    users_repo = MagicMock()
    users_repo.set_last_active_message_id = AsyncMock()

    with (
        patch(
            "handlers.client.menu.disable_previous_menu", new=AsyncMock()
        ) as disable_mock,
        patch("handlers.client.menu.UserRepo", return_value=users_repo),
    ):
        await render_main_menu(message, user, MagicMock())

    disable_mock.assert_not_awaited()
    users_repo.set_last_active_message_id.assert_awaited_once_with(user, 888)


# ---------------------------------------------------------------------------
# on_back_to_main
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_back_to_main_no_message_returns_early() -> None:
    user = make_user()
    callback = AsyncMock()
    callback.message = None
    callback.answer = AsyncMock()
    state = make_fsm_context()

    await on_back_to_main(callback, state, user)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_back_to_main_message_not_editable_returns_early() -> None:
    """callback.message без spec=Message (например, InaccessibleMessage) —
    isinstance-проверка должна отсечь его так же, как None."""
    user = make_user()
    callback = AsyncMock()
    callback.message = AsyncMock()  # не spec=Message -> isinstance() == False
    callback.answer = AsyncMock()
    state = make_fsm_context()

    await on_back_to_main(callback, state, user)

    callback.answer.assert_awaited_once_with()
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_back_to_main_happy_path() -> None:
    user = make_user()
    callback = make_message_callback(CB_MENU_MAIN)
    state = make_fsm_context()
    await state.set_state("some_state")

    await on_back_to_main(callback, state, user)

    assert await state.get_state() is None
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_change_language
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_change_language_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = AsyncMock()
    callback.message = None
    callback.answer = AsyncMock()
    state = make_fsm_context()

    await on_change_language(callback, state, user, db_session)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_change_language_ru_to_en(db_session: AsyncSession) -> None:
    user = make_user(language_code="ru")
    db_session.add(user)
    await db_session.flush()

    callback = make_message_callback(CB_MENU_LANGUAGE)
    state = make_fsm_context()

    await on_change_language(callback, state, user, db_session)

    assert user.language_code == "en"
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_change_language_en_to_ru(db_session: AsyncSession) -> None:
    user = make_user(language_code="en")
    db_session.add(user)
    await db_session.flush()

    callback = make_message_callback(CB_MENU_LANGUAGE)
    state = make_fsm_context()

    await on_change_language(callback, state, user, db_session)

    assert user.language_code == "ru"
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
