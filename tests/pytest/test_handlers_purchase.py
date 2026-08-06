from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from database.enums import PaymentStatus
from database.repo.payments import PaymentRepo
from handlers.client.purchase import (
    on_back_to_servers,
    on_back_to_tariffs,
    on_buy_clicked,
    on_cancel_purchase,
    on_confirm_pay,
    on_server_selected,
    on_tariff_selected,
)
from keyboards.client import CB_MENU_BUY, CB_SERVER_PREFIX, CB_TARIFF_PREFIX
from services.payment import PaymentService
from states.purchase import (
    DATA_IDEMPOTENCY_KEY,
    DATA_PAYMENT_IN_PROGRESS,
    DATA_SERVER_ID,
    DATA_TARIFF_ID,
    PurchaseStates,
)
from tests.pytest.factories import make_server, make_tariff, make_user
from tests.pytest.helpers import make_callback, make_fsm_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# on_buy_clicked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_buy_clicked_no_servers(db_session: AsyncSession) -> None:
    user = make_user()
    callback = make_callback(CB_MENU_BUY)
    state = make_fsm_context()

    await on_buy_clicked(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    _args, kwargs = callback.answer.await_args
    assert kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_on_buy_clicked_with_servers(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff()
    db_session.add_all([user, server, tariff])
    await db_session.flush()
    tariff.server_id = server.id
    await db_session.flush()

    callback = make_callback(CB_MENU_BUY)
    state = make_fsm_context()

    await on_buy_clicked(callback, db_session, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == PurchaseStates.selecting_server.state
    data = await state.get_data()
    assert data[DATA_SERVER_ID] is None
    assert data[DATA_PAYMENT_IN_PROGRESS] is False


# ---------------------------------------------------------------------------
# on_server_selected / _show_tariffs_for_server
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_server_selected_server_unavailable(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SERVER_PREFIX}:999999")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_server)

    await on_server_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_server_selected_no_tariffs(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()

    callback = make_callback(f"{CB_SERVER_PREFIX}:{server.id}")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_server)

    await on_server_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_server_selected_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()

    callback = make_callback(f"{CB_SERVER_PREFIX}:{server.id}")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_server)

    await on_server_selected(callback, db_session, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == PurchaseStates.selecting_tariff.state
    data = await state.get_data()
    assert data[DATA_SERVER_ID] == server.id


@pytest.mark.asyncio
async def test_on_back_to_servers_delegates(
    db_session: AsyncSession, monkeypatch
) -> None:
    user = make_user()
    callback = make_callback(CB_MENU_BUY)
    state = make_fsm_context()

    mocked = AsyncMock()
    monkeypatch.setattr("handlers.client.purchase.on_buy_clicked", mocked)
    await on_back_to_servers(callback, db_session, state, user)
    mocked.assert_awaited_once_with(callback, db_session, state, user)


# ---------------------------------------------------------------------------
# on_tariff_selected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_tariff_selected_unavailable(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_TARIFF_PREFIX}:999999")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_tariff)
    await state.update_data({DATA_SERVER_ID: None})

    await on_tariff_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_tariff_selected_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()

    callback = make_callback(f"{CB_TARIFF_PREFIX}:{tariff.id}")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_tariff)
    await state.update_data({DATA_SERVER_ID: server.id})

    await on_tariff_selected(callback, db_session, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == PurchaseStates.confirming.state
    data = await state.get_data()
    assert data[DATA_TARIFF_ID] == tariff.id
    assert data[DATA_IDEMPOTENCY_KEY] is not None
    assert data[DATA_PAYMENT_IN_PROGRESS] is False


# ---------------------------------------------------------------------------
# on_back_to_tariffs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_back_to_tariffs_no_server_id(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback("menu:back_to_tariffs")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)
    await state.update_data({DATA_SERVER_ID: None})

    await on_back_to_tariffs(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    assert await state.get_state() is None
    assert await state.get_data() == {}


@pytest.mark.asyncio
async def test_on_back_to_tariffs_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()

    callback = make_callback("menu:back_to_tariffs")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)
    await state.update_data({DATA_SERVER_ID: server.id})

    await on_back_to_tariffs(callback, db_session, state, user)

    callback.message.edit_text.assert_awaited_once()
    assert await state.get_state() == PurchaseStates.selecting_tariff.state


# ---------------------------------------------------------------------------
# on_cancel_purchase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_cancel_purchase(db_session: AsyncSession) -> None:
    user = make_user()
    callback = make_callback("menu:cancel")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)
    await state.update_data({DATA_SERVER_ID: 1})

    await on_cancel_purchase(callback, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
    assert await state.get_state() is None
    assert await state.get_data() == {}


# ---------------------------------------------------------------------------
# on_confirm_pay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_confirm_pay_already_in_progress(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback("confirm:pay")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)
    await state.update_data({DATA_PAYMENT_IN_PROGRESS: True})

    await on_confirm_pay(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_confirm_pay_data_expired(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback("confirm:pay")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)
    await state.update_data(
        {
            DATA_PAYMENT_IN_PROGRESS: False,
            DATA_SERVER_ID: 999999,
            DATA_TARIFF_ID: 999999,
            DATA_IDEMPOTENCY_KEY: "some-key",
        }
    )

    await on_confirm_pay(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_on_confirm_pay_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()

    callback = make_callback("confirm:pay")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)
    await state.update_data(
        {
            DATA_PAYMENT_IN_PROGRESS: False,
            DATA_SERVER_ID: server.id,
            DATA_TARIFF_ID: tariff.id,
            DATA_IDEMPOTENCY_KEY: "idem-happy-1",
        }
    )

    await on_confirm_pay(callback, db_session, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == PurchaseStates.awaiting_payment.state

    payments_repo = PaymentRepo(db_session)
    payment = await payments_repo.get_by_idempotence_key("idem-happy-1")
    assert payment is not None
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == tariff.price_amount
    assert payment.confirmation_url is not None


@pytest.mark.asyncio
async def test_on_confirm_pay_create_payment_fails(
    db_session: AsyncSession, monkeypatch
) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()

    callback = make_callback("confirm:pay")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)
    await state.update_data(
        {
            DATA_PAYMENT_IN_PROGRESS: False,
            DATA_SERVER_ID: server.id,
            DATA_TARIFF_ID: tariff.id,
            DATA_IDEMPOTENCY_KEY: "idem-fail-1",
        }
    )

    monkeypatch.setattr(
        PaymentService,
        "create_payment",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    await on_confirm_pay(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()

    data = await state.get_data()
    assert data[DATA_PAYMENT_IN_PROGRESS] is False
    assert await state.get_state() == PurchaseStates.confirming.state
