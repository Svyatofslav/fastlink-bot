from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from config import settings
from database.enums import PaymentProvider
from database.models import Payment, User
from handlers.client.donation import on_donation_amount_entered
from states.donation import DATA_DONATION_PAYMENT_IN_PROGRESS, DonationStates

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def kopecks_to_rub_str(kopecks: int) -> str:
    return str(Decimal(kopecks) / Decimal(100))


async def _make_user(db_session: AsyncSession, telegram_id: int) -> User:
    user = User(
        telegram_id=telegram_id,
        username="donor",
        first_name="Test",
        last_name="Donor",
        language_code="ru",
        is_banned=False,
        is_active=True,
        last_active_at=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _make_message(text: str) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.answer = AsyncMock()
    return message


def _make_state(in_progress: bool = False) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={DATA_DONATION_PAYMENT_IN_PROGRESS: in_progress}
    )
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


async def _count_payments(db_session: AsyncSession, user_id: int) -> int:
    result = await db_session.execute(select(Payment).where(Payment.user_id == user_id))
    return len(list(result.scalars().all()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("amount_str", "should_succeed"),
    [
        (kopecks_to_rub_str(settings.donation_min_amount), True),
        (kopecks_to_rub_str(settings.donation_min_amount - 1), False),
        (kopecks_to_rub_str(settings.donation_max_amount), True),
        (kopecks_to_rub_str(settings.donation_max_amount + 1), False),
    ],
)
async def test_donation_amount_boundaries(
    db_session: AsyncSession, amount_str: str, should_succeed: bool
) -> None:
    user = await _make_user(db_session, telegram_id=hash(amount_str) % 900_000_000 + 1)
    message = _make_message(amount_str)
    state = _make_state()

    await on_donation_amount_entered(message, db_session, state, user)

    payments_count = await _count_payments(db_session, user.id)

    if should_succeed:
        assert payments_count == 1
        state.set_state.assert_awaited_once_with(DonationStates.awaiting_payment)

        result = await db_session.execute(
            select(Payment).where(Payment.user_id == user.id)
        )
        payment = result.scalars().one()
        assert payment.metadata_snapshot["type"] == "donation"
        assert payment.metadata_snapshot["user"]["id"] == user.id
        assert payment.metadata_snapshot["currency"] == "RUB"
    else:
        assert payments_count == 0
        state.set_state.assert_not_awaited()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    ["не число", "abc", "-10", "-50.00", "0", "0.00", ""],
)
async def test_donation_invalid_or_non_positive_amount(
    db_session: AsyncSession, raw_text: str
) -> None:
    user = await _make_user(db_session, telegram_id=hash(raw_text) % 900_000_000 + 1)
    message = _make_message(raw_text)
    state = _make_state()

    await on_donation_amount_entered(message, db_session, state, user)

    assert await _count_payments(db_session, user.id) == 0
    state.set_state.assert_not_awaited()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_donation_amount_comma_and_dot_equivalent(
    db_session: AsyncSession,
) -> None:
    mid_amount_kopecks = (
        settings.donation_min_amount + settings.donation_max_amount
    ) // 2
    rub_value = Decimal(mid_amount_kopecks) / Decimal(100)

    user_dot = await _make_user(db_session, telegram_id=700_000_001)
    message_dot = _make_message(str(rub_value))
    state_dot = _make_state()
    await on_donation_amount_entered(message_dot, db_session, state_dot, user_dot)

    user_comma = await _make_user(db_session, telegram_id=700_000_002)
    message_comma = _make_message(str(rub_value).replace(".", ","))
    state_comma = _make_state()
    await on_donation_amount_entered(message_comma, db_session, state_comma, user_comma)

    result_dot = await db_session.execute(
        select(Payment).where(Payment.user_id == user_dot.id)
    )
    result_comma = await db_session.execute(
        select(Payment).where(Payment.user_id == user_comma.id)
    )
    payment_dot = result_dot.scalars().one()
    payment_comma = result_comma.scalars().one()

    assert payment_dot.amount == payment_comma.amount == mid_amount_kopecks
    assert payment_dot.provider == PaymentProvider.YOOKASSA


@pytest.mark.asyncio
async def test_donation_payment_in_progress_blocks_second_submission(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, telegram_id=700_000_003)
    valid_amount = kopecks_to_rub_str(settings.donation_min_amount)
    message = _make_message(valid_amount)
    state = _make_state(in_progress=True)

    await on_donation_amount_entered(message, db_session, state, user)

    assert await _count_payments(db_session, user.id) == 0
    state.update_data.assert_not_awaited()
    message.answer.assert_awaited_once()
