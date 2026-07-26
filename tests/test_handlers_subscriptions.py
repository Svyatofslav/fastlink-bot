from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from database.enums import SubscriptionStatus
from database.repo.payments import PaymentRepo
from handlers.client.subscriptions import (
    on_my_subscriptions,
    on_subscription_card,
    on_subscription_extend,
    on_subscription_help,
)
from keyboards.client import CB_MENU_MY_SUBS, CB_SUB_PREFIX, CB_SUB_EXTEND, CB_SUB_HELP
from services.payment import PaymentService
from states.purchase import PurchaseStates, DATA_SERVER_ID
from tests.factories import make_user, make_server, make_tariff, make_subscription
from tests.helpers import make_callback, make_fsm_context


# ---------------------------------------------------------------------------
# on_my_subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_my_subscriptions_empty(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(CB_MENU_MY_SUBS)
    state = make_fsm_context()

    await on_my_subscriptions(callback, state, db_session, user)

    callback.message.edit_text.assert_awaited_once()
    args, kwargs = callback.message.edit_text.call_args
    assert "subs.none_yet" not in args[0]  # текст уже переведён, не ключ
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_my_subscriptions_with_subscriptions(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(CB_MENU_MY_SUBS)
    state = make_fsm_context()

    await on_my_subscriptions(callback, state, db_session, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_subscription_card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_subscription_card_invalid_id(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_PREFIX}:not_a_number")
    state = make_fsm_context()

    await on_subscription_card(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_card_not_found(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_PREFIX}:999999")
    state = make_fsm_context()

    await on_subscription_card(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_card_active_shows_link_buttons(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        status=SubscriptionStatus.ACTIVE,
    )
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_PREFIX}:{sub.id}")
    state = make_fsm_context()

    await on_subscription_card(callback, state, db_session, user)

    callback.message.edit_text.assert_awaited_once()
    _, kwargs = callback.message.edit_text.call_args
    markup = kwargs["reply_markup"]
    all_callback_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data is not None
    ]
    assert any("sub:link" in cd for cd in all_callback_data)
    assert any("sub:qr" in cd for cd in all_callback_data)
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_subscription_card_disabled_hides_link_buttons(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        status=SubscriptionStatus.DISABLED,
    )
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_PREFIX}:{sub.id}")
    state = make_fsm_context()

    await on_subscription_card(callback, state, db_session, user)

    _, kwargs = callback.message.edit_text.call_args
    markup = kwargs["reply_markup"]
    all_callback_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data is not None
    ]
    assert not any("sub:link" in cd for cd in all_callback_data)
    assert not any("sub:qr" in cd for cd in all_callback_data)
    # extend/help/back_to_list остаются всегда
    assert any(cd.startswith("sub:extend") for cd in all_callback_data)


# ---------------------------------------------------------------------------
# on_subscription_extend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_subscription_extend_invalid_id(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_EXTEND}:not_a_number")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_extend_not_found(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_EXTEND}:999999")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_extend_no_server_id(
    db_session: AsyncSession, monkeypatch
) -> None:
    from database.repo.subscriptions import SubscriptionRepo

    user = make_user()
    db_session.add(user)
    await db_session.flush()

    fake_sub = make_subscription(user_id=user.id, server_id=1, tariff_id=None)
    fake_sub.server_id = None  # не персистим в БД, просто in-memory объект

    monkeypatch.setattr(SubscriptionRepo, "get_by_id", AsyncMock(return_value=fake_sub))

    callback = make_callback(f"{CB_SUB_EXTEND}:{fake_sub.id}")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_extend_server_unavailable(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server(is_active=False)
    db_session.add_all([user, server])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=None)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_EXTEND}:{sub.id}")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_extend_with_active_tariff_happy_path(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_EXTEND}:{sub.id}")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()

    payments_repo = PaymentRepo(db_session)
    payments = await payments_repo.get_by_subscription(sub.id)
    assert len(payments) == 1
    assert payments[0].amount == tariff.price_amount
    assert payments[0].metadata_snapshot["flags"]["is_extend"] is True
    assert payments[0].metadata_snapshot["flags"]["extend_subscription_id"] == sub.id


@pytest.mark.asyncio
async def test_on_subscription_extend_create_payment_fails(
    db_session: AsyncSession, monkeypatch
) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    monkeypatch.setattr(
        PaymentService,
        "create_payment",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    callback = make_callback(f"{CB_SUB_EXTEND}:{sub.id}")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_extend_tariff_unavailable_falls_back_to_tariff_selection(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    inactive_tariff = make_tariff(server_id=server.id, is_active=False)
    active_tariff = make_tariff(server_id=server.id, is_active=True)
    db_session.add_all([user, server, inactive_tariff, active_tariff])
    await db_session.flush()

    sub = make_subscription(
        user_id=user.id, server_id=server.id, tariff_id=inactive_tariff.id
    )
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_EXTEND}:{sub.id}")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == PurchaseStates.selecting_tariff.state

    data = await state.get_data()
    assert data[DATA_SERVER_ID] == server.id

    payments_repo = PaymentRepo(db_session)
    payments = await payments_repo.get_by_subscription(sub.id)
    assert len(payments) == 0


@pytest.mark.asyncio
async def test_on_subscription_extend_no_tariffs_for_server(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=None)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_EXTEND}:{sub.id}")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True
    assert await state.get_state() is None


# ---------------------------------------------------------------------------
# on_subscription_help
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_subscription_help_invalid_id(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_HELP}:not_a_number")
    state = make_fsm_context()

    await on_subscription_help(callback, state, db_session, user)

    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_on_subscription_help_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_HELP}:42")
    state = make_fsm_context()

    await on_subscription_help(callback, state, db_session, user)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()
