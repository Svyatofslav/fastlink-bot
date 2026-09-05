from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database.enums import SubscriptionStatus
from handlers.client.subscriptions import (
    _build_subscription_card_context,
    _get_callback_message,
    _get_marzban_config_link,
    _get_owned_subscription,
    _make_qr_bytes,
    _prepare_subscription_action,
    on_my_subscriptions,
    on_subscription_card,
    on_subscription_config_link,
    on_subscription_config_qr,
    on_subscription_extend,
    on_subscription_help,
    on_subscription_link,
    on_subscription_qr,
)
from keyboards.client import (
    CB_MENU_MY_SUBS,
    CB_SUB_CONFIG_LINK,
    CB_SUB_CONFIG_QR,
    CB_SUB_EXTEND,
    CB_SUB_HELP,
    CB_SUB_LINK,
    CB_SUB_PREFIX,
    CB_SUB_QR,
)
from tests.pytest.factories import (
    make_server,
    make_subscription,
    make_tariff,
    make_user,
)
from tests.pytest.helpers import make_callback, make_fsm_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def make_callback_no_message(data: str) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.message = None
    callback.answer = AsyncMock()
    return callback


def make_marzban_mock(
    *,
    get_user_side_effect=None,
    config_link: str | None = "https://config.example/link1",
) -> MagicMock:
    marzban = MagicMock()
    if get_user_side_effect is not None:
        marzban.get_user = AsyncMock(side_effect=get_user_side_effect)
    else:
        marzban.get_user = AsyncMock(return_value=MagicMock())
    marzban.aclose = AsyncMock()
    marzban.get_primary_config_link = MagicMock(return_value=config_link)
    return marzban


# ---------------------------------------------------------------------------
# _get_callback_message
# ---------------------------------------------------------------------------


def test_get_callback_message_none_when_message_is_none() -> None:
    callback = SimpleNamespace(message=None)
    assert _get_callback_message(callback) is None


def test_get_callback_message_none_when_no_edit_text() -> None:
    callback = SimpleNamespace(message=SimpleNamespace())
    assert _get_callback_message(callback) is None


def test_get_callback_message_returns_message_when_editable() -> None:
    message = SimpleNamespace(edit_text=lambda *a, **kw: None)
    callback = SimpleNamespace(message=message)
    assert _get_callback_message(callback) is message


# ---------------------------------------------------------------------------
# _build_subscription_card_context — недостающие ветки (tariff=None, data_limit=0)
# ---------------------------------------------------------------------------


def test_build_subscription_card_context_no_tariff_no_traffic() -> None:
    subscription = SimpleNamespace(
        status=SubscriptionStatus.ACTIVE,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=0,
        data_used_bytes=0,
    )

    result = _build_subscription_card_context(subscription, None, None, "ru")

    assert result["price_line"] == ""
    assert result["traffic_line"] == ""
    assert result["server_name"] != ""
    assert result["tariff_name"] != ""


def test_build_subscription_card_context_with_tariff_and_traffic() -> None:
    server = SimpleNamespace(name="Server 1")
    tariff = SimpleNamespace(name="Tariff 1", price_amount=10000, price_currency="RUB")
    subscription = SimpleNamespace(
        status=SubscriptionStatus.DISABLED,
        starts_at=None,
        expires_at=None,
        data_limit_bytes=1000,
        data_used_bytes=500,
    )

    result = _build_subscription_card_context(subscription, server, tariff, "ru")

    assert result["price_line"] != ""
    assert result["traffic_line"] != ""
    assert result["server_name"] == "Server 1"
    assert result["tariff_name"] == "Tariff 1"


# ---------------------------------------------------------------------------
# _make_qr_bytes
# ---------------------------------------------------------------------------


def test_make_qr_bytes_returns_non_empty_bytes() -> None:
    result = _make_qr_bytes("https://example.com/sub/1")

    assert isinstance(result, bytes)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# _get_owned_subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_owned_subscription_invalid_id_returns_none(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_LINK}:not_a_number")

    result = await _get_owned_subscription(callback, db_session, user, CB_SUB_LINK)

    assert result is None
    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_get_owned_subscription_not_found_returns_none(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_LINK}:999999")

    result = await _get_owned_subscription(callback, db_session, user, CB_SUB_LINK)

    assert result is None
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_owned_subscription_wrong_owner_returns_none(
    db_session: AsyncSession,
) -> None:
    owner = make_user()
    other_user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([owner, other_user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=owner.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_LINK}:{sub.id}")

    result = await _get_owned_subscription(
        callback, db_session, other_user, CB_SUB_LINK
    )

    assert result is None
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_owned_subscription_success_returns_subscription(
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

    callback = make_callback(f"{CB_SUB_LINK}:{sub.id}")

    result = await _get_owned_subscription(callback, db_session, user, CB_SUB_LINK)

    assert result is not None
    assert result.id == sub.id
    callback.answer.assert_not_awaited()


# ---------------------------------------------------------------------------
# _get_marzban_config_link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_marzban_config_link_success() -> None:
    subscription = SimpleNamespace(marzban_username="user1")
    callback = make_callback("irrelevant")
    marzban_mock = make_marzban_mock(config_link="https://config.example/ok")

    with patch(
        "handlers.client.subscriptions.MarzbanClient", return_value=marzban_mock
    ):
        result = await _get_marzban_config_link(subscription, "ru", callback)

    assert result == "https://config.example/ok"
    marzban_mock.aclose.assert_awaited_once()
    callback.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_marzban_config_link_marzban_error_returns_none() -> None:
    from clients.marzban import MarzbanClientError

    subscription = SimpleNamespace(marzban_username="user1")
    callback = make_callback("irrelevant")
    marzban_mock = make_marzban_mock(get_user_side_effect=MarzbanClientError("boom"))

    with patch(
        "handlers.client.subscriptions.MarzbanClient", return_value=marzban_mock
    ):
        result = await _get_marzban_config_link(subscription, "ru", callback)

    assert result is None
    marzban_mock.aclose.assert_awaited_once()
    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_get_marzban_config_link_no_link_available_returns_none() -> None:
    subscription = SimpleNamespace(marzban_username="user1")
    callback = make_callback("irrelevant")
    marzban_mock = make_marzban_mock(config_link=None)

    with patch(
        "handlers.client.subscriptions.MarzbanClient", return_value=marzban_mock
    ):
        result = await _get_marzban_config_link(subscription, "ru", callback)

    assert result is None
    marzban_mock.aclose.assert_awaited_once()
    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


# ---------------------------------------------------------------------------
# _prepare_subscription_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_subscription_action_no_message_returns_none(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback_no_message(f"{CB_SUB_LINK}:1")

    result = await _prepare_subscription_action(callback, db_session, user, CB_SUB_LINK)

    assert result is None
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_prepare_subscription_action_subscription_not_found_returns_none(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_LINK}:999999")

    result = await _prepare_subscription_action(callback, db_session, user, CB_SUB_LINK)

    assert result is None


@pytest.mark.asyncio
async def test_prepare_subscription_action_success(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_LINK}:{sub.id}")

    result = await _prepare_subscription_action(callback, db_session, user, CB_SUB_LINK)

    assert result is not None
    _message, subscription = result
    assert subscription.id == sub.id


# ---------------------------------------------------------------------------
# on_my_subscriptions — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_my_subscriptions_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback_no_message(CB_MENU_MY_SUBS)
    state = make_fsm_context()

    await on_my_subscriptions(callback, state, db_session, user)

    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_subscription_card — недостающая ветка (message None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_subscription_card_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback_no_message(f"{CB_SUB_PREFIX}:1")
    state = make_fsm_context()

    await on_subscription_card(callback, state, db_session, user)

    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_subscription_extend / on_subscription_help — недостающая ветка (message None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_subscription_extend_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback_no_message(f"{CB_SUB_EXTEND}:1")
    state = make_fsm_context()

    await on_subscription_extend(callback, state, db_session, user)

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_subscription_help_no_message_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback_no_message(f"{CB_SUB_HELP}:1")
    state = make_fsm_context()

    await on_subscription_help(callback, state, db_session, user)

    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_subscription_link / on_subscription_qr
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_subscription_link_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_LINK}:{sub.id}")

    with patch(
        "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
    ) as render_menu:
        await on_subscription_link(callback, db_session, user)

    callback.message.answer.assert_awaited_once()
    render_menu.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_subscription_link_not_owned_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_LINK}:999999")

    with patch(
        "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
    ) as render_menu:
        await on_subscription_link(callback, db_session, user)

    render_menu.assert_not_awaited()
    callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_subscription_qr_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_QR}:{sub.id}")

    with patch(
        "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
    ) as render_menu:
        await on_subscription_qr(callback, db_session, user)

    callback.message.answer_photo.assert_awaited_once()
    _, kwargs = callback.message.answer_photo.call_args
    assert kwargs["caption"] is not None
    render_menu.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# on_subscription_config_link / on_subscription_config_qr
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_subscription_config_link_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_CONFIG_LINK}:{sub.id}")
    marzban_mock = make_marzban_mock(config_link="https://config.example/link1")

    with (
        patch("handlers.client.subscriptions.MarzbanClient", return_value=marzban_mock),
        patch(
            "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
        ) as render_menu,
    ):
        await on_subscription_config_link(callback, db_session, user)

    callback.message.answer.assert_awaited_once()
    render_menu.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_subscription_config_link_marzban_failure_returns_early(
    db_session: AsyncSession,
) -> None:
    from clients.marzban import MarzbanClientError

    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_CONFIG_LINK}:{sub.id}")
    marzban_mock = make_marzban_mock(get_user_side_effect=MarzbanClientError("boom"))

    with (
        patch("handlers.client.subscriptions.MarzbanClient", return_value=marzban_mock),
        patch(
            "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
        ) as render_menu,
    ):
        await on_subscription_config_link(callback, db_session, user)

    callback.message.answer.assert_not_awaited()
    render_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_subscription_config_qr_happy_path(db_session: AsyncSession) -> None:
    user = make_user()
    server = make_server()
    tariff = make_tariff(server_id=server.id)
    db_session.add_all([user, server, tariff])
    await db_session.flush()

    sub = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add(sub)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_CONFIG_QR}:{sub.id}")
    marzban_mock = make_marzban_mock(config_link="https://config.example/link2")

    with (
        patch("handlers.client.subscriptions.MarzbanClient", return_value=marzban_mock),
        patch(
            "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
        ) as render_menu,
    ):
        await on_subscription_config_qr(callback, db_session, user)

    callback.message.answer_photo.assert_awaited_once()
    render_menu.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_on_subscription_qr_not_owned_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_QR}:999999")

    with patch(
        "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
    ) as render_menu:
        await on_subscription_qr(callback, db_session, user)

    callback.message.answer_photo.assert_not_awaited()
    render_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_subscription_config_link_not_owned_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_CONFIG_LINK}:999999")

    with (
        patch("handlers.client.subscriptions.MarzbanClient") as marzban_cls,
        patch(
            "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
        ) as render_menu,
    ):
        await on_subscription_config_link(callback, db_session, user)

    marzban_cls.assert_not_called()
    callback.message.answer.assert_not_awaited()
    render_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_subscription_config_qr_not_owned_returns_early(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()

    callback = make_callback(f"{CB_SUB_CONFIG_QR}:999999")

    with (
        patch("handlers.client.subscriptions.MarzbanClient") as marzban_cls,
        patch(
            "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
        ) as render_menu,
    ):
        await on_subscription_config_qr(callback, db_session, user)

    marzban_cls.assert_not_called()
    callback.message.answer_photo.assert_not_awaited()
    render_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_subscription_config_qr_no_config_link_returns_early(
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

    callback = make_callback(f"{CB_SUB_CONFIG_QR}:{sub.id}")
    marzban_mock = make_marzban_mock(config_link=None)

    with (
        patch("handlers.client.subscriptions.MarzbanClient", return_value=marzban_mock),
        patch(
            "handlers.client.subscriptions.render_main_menu", new=AsyncMock()
        ) as render_menu,
    ):
        await on_subscription_config_qr(callback, db_session, user)

    callback.message.answer_photo.assert_not_awaited()
    render_menu.assert_not_awaited()
    callback.answer.assert_awaited_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_extend_via_tariff_selection_stores_extend_marker_in_fsm(monkeypatch):
    """
    Регрессия: раньше _extend_via_tariff_selection сохранял в FSM только
    build_purchase_data(), без build_extend_data(subscription.id). Из-за
    этого после выбора нового тарифа покупка создавала НОВУЮ подписку
    вместо продления старой — пользователь терял старую подписку молча.
    """
    from handlers.client.subscriptions import on_subscription_extend
    from states.purchase import (
        DATA_EXTEND_SUBSCRIPTION_ID,
        DATA_IS_EXTEND,
        DATA_SERVER_ID,
    )

    subscription = SimpleNamespace(id=42, user_id=1, server_id=5, tariff_id=None)
    server = SimpleNamespace(id=5, name="Server-5")

    subs_repo = AsyncMock()
    subs_repo.get_by_id = AsyncMock(return_value=subscription)
    tariffs_repo = AsyncMock()
    tariffs_repo.get_by_id_active = AsyncMock(return_value=None)
    tariffs_repo.get_active_by_server = AsyncMock(
        return_value=[SimpleNamespace(id=1, price_amount=1000, name="Тариф 1")]
    )
    servers_repo = AsyncMock()
    servers_repo.get_by_id_active = AsyncMock(return_value=server)

    monkeypatch.setattr(
        "handlers.client.subscriptions.SubscriptionRepo", lambda session: subs_repo
    )
    monkeypatch.setattr(
        "handlers.client.subscriptions.TariffRepo", lambda session: tariffs_repo
    )
    monkeypatch.setattr(
        "handlers.client.subscriptions.ServerRepo", lambda session: servers_repo
    )
    monkeypatch.setattr(
        "handlers.client.subscriptions._get_callback_message",
        lambda callback: AsyncMock(),
    )
    monkeypatch.setattr(
        "handlers.client.subscriptions._extract_callback_id",
        lambda data, prefix: subscription.id,
    )

    callback = MagicMock(data=f"sub:extend:{subscription.id}")
    callback.answer = AsyncMock()
    state = AsyncMock()
    user = SimpleNamespace(id=1, language_code="ru")

    await on_subscription_extend(callback, state, MagicMock(), user)

    stored: dict = {}
    for call in state.update_data.await_args_list:
        if call.args:
            stored.update(call.args[0])
        stored.update(call.kwargs)

    assert stored.get(DATA_IS_EXTEND) is True
    assert stored.get(DATA_EXTEND_SUBSCRIPTION_ID) == subscription.id
    assert stored.get(DATA_SERVER_ID) == server.id
