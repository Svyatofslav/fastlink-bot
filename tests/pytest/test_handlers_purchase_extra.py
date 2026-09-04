from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from handlers.client.purchase import (
    _get_callback_message,
    _load_validated_purchase_context,
    on_back_to_tariffs,
    on_buy_clicked,
    on_cancel_purchase,
    on_confirm_pay,
    on_server_selected,
    on_tariff_selected,
)
from keyboards.client import CB_MENU_BUY, CB_SERVER_PREFIX, CB_TARIFF_PREFIX
from states.purchase import (
    DATA_IDEMPOTENCY_KEY,
    DATA_SERVER_ID,
    DATA_TARIFF_ID,
    PurchaseStates,
)
from tests.pytest.factories import make_server, make_tariff, make_user
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
# _get_callback_message
# ---------------------------------------------------------------------------


def test_get_callback_message_none_when_no_message() -> None:
    callback = make_callback_no_message("irrelevant")
    assert _get_callback_message(callback) is None


# ---------------------------------------------------------------------------
# _load_validated_purchase_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_validated_purchase_context_missing_server_id(
    db_session: AsyncSession,
) -> None:
    result = await _load_validated_purchase_context(
        db_session,
        {DATA_TARIFF_ID: 1, DATA_IDEMPOTENCY_KEY: "key"},
    )
    assert result is None


@pytest.mark.asyncio
async def test_load_validated_purchase_context_missing_tariff_id(
    db_session: AsyncSession,
) -> None:
    result = await _load_validated_purchase_context(
        db_session,
        {DATA_SERVER_ID: 1, DATA_IDEMPOTENCY_KEY: "key"},
    )
    assert result is None


@pytest.mark.asyncio
async def test_load_validated_purchase_context_missing_idempotency_key(
    db_session: AsyncSession,
) -> None:
    result = await _load_validated_purchase_context(
        db_session,
        {DATA_SERVER_ID: 1, DATA_TARIFF_ID: 1},
    )
    assert result is None


@pytest.mark.asyncio
async def test_load_validated_purchase_context_empty_idempotency_key(
    db_session: AsyncSession,
) -> None:
    result = await _load_validated_purchase_context(
        db_session,
        {DATA_SERVER_ID: 1, DATA_TARIFF_ID: 1, DATA_IDEMPOTENCY_KEY: ""},
    )
    assert result is None


@pytest.mark.asyncio
async def test_load_validated_purchase_context_success(
    db_session: AsyncSession,
) -> None:
    server = make_server()
    db_session.add(server)
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()

    result = await _load_validated_purchase_context(
        db_session,
        {
            DATA_SERVER_ID: server.id,
            DATA_TARIFF_ID: tariff.id,
            DATA_IDEMPOTENCY_KEY: "key-1",
        },
    )

    assert result is not None
    result_server, result_tariff, key = result
    assert result_server.id == server.id
    assert result_tariff.id == tariff.id
    assert key == "key-1"


# ---------------------------------------------------------------------------
# on_buy_clicked — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_buy_clicked_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = make_callback_no_message(CB_MENU_BUY)
    state = make_fsm_context()

    await on_buy_clicked(callback, db_session, state, user)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_buy_clicked_server_without_tariffs_skips_min_price(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()

    callback = make_callback(CB_MENU_BUY)
    state = make_fsm_context()

    await on_buy_clicked(callback, db_session, state, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_server_selected / _show_tariffs_for_server — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_server_selected_malformed_callback_data(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SERVER_PREFIX}:not_a_number")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_server)

    await on_server_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_server_selected_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()

    callback = make_callback_no_message(f"{CB_SERVER_PREFIX}:{server.id}")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_server)

    await on_server_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_tariff_selected — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_tariff_selected_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = make_callback_no_message(f"{CB_TARIFF_PREFIX}:1")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_tariff)

    await on_tariff_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_tariff_selected_malformed_callback_data(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_TARIFF_PREFIX}:not_a_number")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.selecting_tariff)
    await state.update_data({DATA_SERVER_ID: 1})

    await on_tariff_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_tariff_selected_missing_server_id_in_state(
    db_session: AsyncSession,
) -> None:
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
    # DATA_SERVER_ID отсутствует в state

    await on_tariff_selected(callback, db_session, state, user)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_back_to_tariffs — недостающая ветка (message None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_back_to_tariffs_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = make_callback_no_message("menu:back_to_tariffs")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)

    await on_back_to_tariffs(callback, db_session, state, user)

    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_cancel_purchase — недостающая ветка (message None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_cancel_purchase_no_message_returns_early() -> None:
    user = make_user()
    callback = make_callback_no_message("menu:cancel")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)

    await on_cancel_purchase(callback, state, user)

    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_confirm_pay — недостающая ветка (message None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_confirm_pay_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    callback = make_callback_no_message("confirm:pay")
    state = make_fsm_context()
    await state.set_state(PurchaseStates.confirming)

    await on_confirm_pay(callback, db_session, state, user)

    callback.answer.assert_awaited_once_with()
