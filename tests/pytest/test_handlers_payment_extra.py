from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from database.enums import PaymentStatus
from handlers.client.payment import (
    _extract_payment_id,
    on_payment_cancel,
    on_payment_check,
)
from keyboards.client import CB_PAYMENT_CANCEL, CB_PAYMENT_CHECK
from tests.pytest.factories import make_payment, make_user
from tests.pytest.helpers import make_callback, make_fsm_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def make_callback_no_message(data: str) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.message = None
    callback.answer = AsyncMock()
    return callback


# ---------------------------------------------------------------------------
# _extract_payment_id
# ---------------------------------------------------------------------------


def test_extract_payment_id_none_data_returns_none() -> None:
    assert _extract_payment_id(None, CB_PAYMENT_CHECK) is None


def test_extract_payment_id_wrong_prefix_returns_none() -> None:
    assert _extract_payment_id("other:123", CB_PAYMENT_CHECK) is None


def test_extract_payment_id_non_digit_suffix_returns_none() -> None:
    assert _extract_payment_id(f"{CB_PAYMENT_CHECK}:abc", CB_PAYMENT_CHECK) is None


def test_extract_payment_id_valid_returns_int() -> None:
    assert _extract_payment_id(f"{CB_PAYMENT_CHECK}:42", CB_PAYMENT_CHECK) == 42


# ---------------------------------------------------------------------------
# on_payment_check — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_payment_check_malformed_callback_data(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = make_callback(f"{CB_PAYMENT_CHECK}:not_a_number")

    await on_payment_check(callback, db_session, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_payment_check_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(user_id=user.id, status=PaymentStatus.PENDING)
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback_no_message(f"{CB_PAYMENT_CHECK}:{payment.id}")

    await on_payment_check(callback, db_session, user)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_payment_check_refunded_status_shows_generic_status(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(user_id=user.id, status=PaymentStatus.REFUNDED_PARTIALLY)
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CHECK}:{payment.id}")

    await on_payment_check(callback, db_session, user)

    callback.answer.assert_awaited_once()
    call_args = callback.answer.await_args
    assert "refunded_partially" in call_args.args[0]
    assert call_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_payment_cancel — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_payment_cancel_malformed_callback_data(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = make_callback(f"{CB_PAYMENT_CANCEL}:not_a_number")
    state = make_fsm_context()

    await on_payment_cancel(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_payment_cancel_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(user_id=user.id, status=PaymentStatus.PENDING)
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback_no_message(f"{CB_PAYMENT_CANCEL}:{payment.id}")
    state = make_fsm_context()

    await on_payment_cancel(callback, db_session, state, user)

    callback.answer.assert_awaited_once_with()
