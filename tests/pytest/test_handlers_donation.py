from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from config import settings
from database.enums import PaymentStatus
from database.repo.payments import PaymentRepo
from handlers.client.donation import on_donate_clicked, on_donation_amount_entered
from keyboards.client import CB_MENU_DONATE
from services.payment import PaymentService
from states.donation import DATA_DONATION_PAYMENT_IN_PROGRESS, DonationStates
from tests.pytest.factories import make_user
from tests.pytest.helpers import make_callback, make_fsm_context, make_message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# on_donate_clicked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donate_clicked_sets_state_and_shows_prompt() -> None:
    user = make_user()
    callback = make_callback(CB_MENU_DONATE)
    state = make_fsm_context()

    await on_donate_clicked(callback, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == DonationStates.waiting_for_amount.state


# ---------------------------------------------------------------------------
# on_donation_amount_entered — валидация суммы
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donation_amount_entered_invalid_text(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    message = make_message("не число")
    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)

    await on_donation_amount_entered(message, db_session, state, user)

    message.answer.assert_awaited_once()
    assert await state.get_state() == DonationStates.waiting_for_amount.state


@pytest.mark.asyncio
async def test_on_donation_amount_entered_too_small(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    too_small_rub = (settings.donation_min_amount - 1) / 100
    message = make_message(str(too_small_rub))
    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)

    await on_donation_amount_entered(message, db_session, state, user)

    message.answer.assert_awaited_once()
    assert await state.get_state() == DonationStates.waiting_for_amount.state


@pytest.mark.asyncio
async def test_on_donation_amount_entered_too_large(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    too_large_rub = (settings.donation_max_amount + 1) / 100
    message = make_message(str(too_large_rub))
    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)

    await on_donation_amount_entered(message, db_session, state, user)

    message.answer.assert_awaited_once()
    assert await state.get_state() == DonationStates.waiting_for_amount.state


# ---------------------------------------------------------------------------
# on_donation_amount_entered — payment_in_progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donation_amount_entered_already_in_progress(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    valid_rub = settings.donation_min_amount / 100
    message = make_message(str(valid_rub))
    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)
    await state.update_data({DATA_DONATION_PAYMENT_IN_PROGRESS: True})

    await on_donation_amount_entered(message, db_session, state, user)

    message.answer.assert_awaited_once()
    data = await state.get_data()
    assert data[DATA_DONATION_PAYMENT_IN_PROGRESS] is True
    assert await state.get_state() == DonationStates.waiting_for_amount.state


# ---------------------------------------------------------------------------
# on_donation_amount_entered — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donation_amount_entered_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    valid_rub = settings.donation_min_amount / 100
    message = make_message(str(valid_rub))
    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)

    await on_donation_amount_entered(message, db_session, state, user)

    message.answer.assert_awaited_once()
    assert await state.get_state() == DonationStates.awaiting_payment.state

    data = await state.get_data()
    assert data[DATA_DONATION_PAYMENT_IN_PROGRESS] is True

    payments_repo = PaymentRepo(db_session)
    payments = await payments_repo.get_all_by_user(user.id)
    assert len(payments) == 1
    payment = payments[0]
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == settings.donation_min_amount
    assert payment.subscription_id is None
    assert payment.metadata_snapshot["type"] == "donation"


# ---------------------------------------------------------------------------
# on_donation_amount_entered — create_payment бросает исключение
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_donation_amount_entered_create_payment_fails(
    db_session: AsyncSession, monkeypatch
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    valid_rub = settings.donation_min_amount / 100
    message = make_message(str(valid_rub))
    state = make_fsm_context()
    await state.set_state(DonationStates.waiting_for_amount)

    monkeypatch.setattr(
        PaymentService,
        "create_payment",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    await on_donation_amount_entered(message, db_session, state, user)

    message.answer.assert_awaited_once()
    data = await state.get_data()
    assert data[DATA_DONATION_PAYMENT_IN_PROGRESS] is False
    assert await state.get_state() == DonationStates.waiting_for_amount.state
