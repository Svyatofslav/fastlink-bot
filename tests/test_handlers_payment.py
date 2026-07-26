from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import PaymentStatus
from handlers.client.payment import on_payment_cancel, on_payment_check
from keyboards.client import CB_PAYMENT_CANCEL, CB_PAYMENT_CHECK
from states.purchase import PurchaseStates, build_purchase_data
from tests.factories import make_payment, make_user
from tests.helpers import make_callback, make_fsm_context


# ---------------------------------------------------------------------------
# on_payment_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_payment_check_not_found(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CHECK}:999999")

    await on_payment_check(callback, db_session, user)

    callback.answer.assert_awaited_once()
    args, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_payment_check_pending(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(user_id=user.id, status=PaymentStatus.PENDING)
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CHECK}:{payment.id}")

    await on_payment_check(callback, db_session, user)

    callback.answer.assert_awaited_once()
    args, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_payment_check_succeeded(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(
        user_id=user.id, status=PaymentStatus.SUCCEEDED, amount=29900
    )
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CHECK}:{payment.id}")

    await on_payment_check(callback, db_session, user)

    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_payment_check_canceled(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(user_id=user.id, status=PaymentStatus.CANCELED)
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CHECK}:{payment.id}")

    await on_payment_check(callback, db_session, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_payment_cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_payment_cancel_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(user_id=user.id, status=PaymentStatus.PENDING)
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CANCEL}:{payment.id}")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.awaiting_payment)
    await state.update_data(build_purchase_data())

    await on_payment_cancel(callback, db_session, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()

    assert await state.get_data() == {}
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_on_payment_cancel_impossible_when_not_pending(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    payment = make_payment(user_id=user.id, status=PaymentStatus.SUCCEEDED)
    db_session.add(payment)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CANCEL}:{payment.id}")
    state = make_fsm_context()

    await on_payment_cancel(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    args, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_payment_cancel_not_found_shows_alert(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_PAYMENT_CANCEL}:999999")
    state = make_fsm_context()

    await on_payment_cancel(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    args, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()
    assert await state.get_state() is None
