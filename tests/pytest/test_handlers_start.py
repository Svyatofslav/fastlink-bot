from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Message

from handlers.client.start import start_handler
from tests.pytest.factories import make_user
from tests.pytest.helpers import make_fsm_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def make_start_message(message_date: datetime) -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.date = message_date
    message.answer = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_start_handler_new_user_shows_welcome_new(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    user = make_user()
    user.created_at = now  # не персистим в БД — только in-memory, чтобы не зависеть
    # от возможного DB-триггера, перезаписывающего created_at при flush().

    message = make_start_message(now)
    state = make_fsm_context()
    await state.set_state("some_state")

    with patch(
        "handlers.client.start.render_main_menu", new=AsyncMock()
    ) as render_menu_mock:
        await start_handler(message, state, user, db_session)

    assert await state.get_state() is None
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] is not None
    render_menu_mock.assert_awaited_once_with(message, user, db_session)


@pytest.mark.asyncio
async def test_start_handler_returning_user_shows_welcome_returning(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    user.created_at = datetime.now(UTC) - timedelta(days=30)

    message = make_start_message(datetime.now(UTC))
    state = make_fsm_context()

    with patch(
        "handlers.client.start.render_main_menu", new=AsyncMock()
    ) as render_menu_mock:
        await start_handler(message, state, user, db_session)

    message.answer.assert_awaited_once()
    render_menu_mock.assert_awaited_once_with(message, user, db_session)


@pytest.mark.asyncio
async def test_start_handler_no_message_date_treated_as_returning(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    user.created_at = datetime.now(UTC)

    message = AsyncMock(spec=Message)
    message.date = None
    message.answer = AsyncMock()
    state = make_fsm_context()

    with patch("handlers.client.start.render_main_menu", new=AsyncMock()):
        await start_handler(message, state, user, db_session)

    message.answer.assert_awaited_once()
