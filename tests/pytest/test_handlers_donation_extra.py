from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from handlers.client.donation import on_donate_clicked, on_donation_cancel
from keyboards.client import CB_DONATION_CANCEL, CB_MENU_DONATE
from tests.pytest.factories import make_user
from tests.pytest.helpers import make_fsm_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def make_callback_with_message(data: str, message) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.message = message
    callback.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# on_donate_clicked — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donate_clicked_no_message_returns_early() -> None:
    user = make_user()
    callback = make_callback_with_message(CB_MENU_DONATE, None)
    state = make_fsm_context()

    await on_donate_clicked(callback, state, user)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_donate_clicked_message_without_edit_text_returns_early() -> None:
    user = make_user()
    non_editable_message = SimpleNamespace()  # нет атрибута edit_text
    callback = make_callback_with_message(CB_MENU_DONATE, non_editable_message)
    state = make_fsm_context()

    await on_donate_clicked(callback, state, user)

    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_donation_amount_entered — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donation_amount_entered_text_is_none(
    db_session: AsyncSession,
) -> None:
    from handlers.client.donation import on_donation_amount_entered
    from states.donation import DonationStates

    user = make_user()
    db_session.add(user)
    await db_session.flush()

    message = AsyncMock(spec=Message)
    message.text = None
    message.answer = AsyncMock()

    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)

    await on_donation_amount_entered(message, db_session, state, user)

    message.answer.assert_awaited_once()
    assert await state.get_state() == DonationStates.waiting_for_amount.state


@pytest.mark.asyncio
async def test_on_donation_amount_entered_no_bot_skips_disable_previous_menu(
    db_session: AsyncSession,
) -> None:
    from config import settings
    from handlers.client.donation import on_donation_amount_entered
    from states.donation import DonationStates

    user = make_user()
    db_session.add(user)
    await db_session.flush()

    valid_rub = settings.donation_min_amount / 100
    message = AsyncMock(spec=Message)
    message.text = str(valid_rub)
    message.bot = None
    message.chat = MagicMock(id=1)
    message.answer = AsyncMock(return_value=MagicMock(message_id=123))

    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)

    with patch(
        "handlers.client.donation.disable_previous_menu", new=AsyncMock()
    ) as disable_mock:
        await on_donation_amount_entered(message, db_session, state, user)

    disable_mock.assert_not_awaited()
    message.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# on_donation_cancel — вообще не было тестов
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donation_cancel_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = make_callback_with_message(CB_DONATION_CANCEL, None)
    state = make_fsm_context()

    await on_donation_cancel(callback, state, user, db_session)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_donation_cancel_message_not_instance_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    non_message = SimpleNamespace(edit_text=AsyncMock())
    callback = make_callback_with_message(CB_DONATION_CANCEL, non_message)
    state = make_fsm_context()

    await on_donation_cancel(callback, state, user, db_session)

    callback.answer.assert_awaited_once_with()
    non_message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_donation_cancel_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    message = AsyncMock(spec=Message)
    message.edit_text = AsyncMock()
    callback = make_callback_with_message(CB_DONATION_CANCEL, message)
    state = make_fsm_context()
    await state.set_state("some_state")

    with patch(
        "handlers.client.donation.render_main_menu", new=AsyncMock()
    ) as render_menu_mock:
        await on_donation_cancel(callback, state, user, db_session)

    assert await state.get_state() is None
    message.edit_text.assert_awaited_once()
    render_menu_mock.assert_awaited_once_with(message, user, db_session)
    callback.answer.assert_awaited_once_with()
