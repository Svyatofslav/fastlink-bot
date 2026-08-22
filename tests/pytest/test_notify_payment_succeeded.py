# tests/test_notify_payment_succeeded.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from keyboards.client import main_menu_kb
from scheduler.jobs import _notify_payment_succeeded
from utils.format import format_price
from utils.i18n import t


def make_user(telegram_id: int = 123456, language_code: str = "ru") -> SimpleNamespace:
    return SimpleNamespace(id=1, telegram_id=telegram_id, language_code=language_code)


def make_payment(
    user: SimpleNamespace, amount: int = 29900, currency: str = "RUB"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        user_id=user.id,
        subscription_id=None,
        amount=amount,
        currency=currency,
    )


def make_notifications_mock(should_send: bool = True) -> MagicMock:
    notifications = MagicMock()
    notifications.should_send = AsyncMock(return_value=should_send)
    notifications.log_success = AsyncMock()
    notifications.log_failure = AsyncMock()
    return notifications


def make_user_repo_mock(user: SimpleNamespace) -> MagicMock:
    users_repo = MagicMock()
    users_repo.get_by_id = AsyncMock(return_value=user)
    return users_repo


@pytest.mark.asyncio
async def test_notify_payment_succeeded_happy_path() -> None:
    user = make_user()
    payment = make_payment(user)
    bot = AsyncMock()
    notifications = make_notifications_mock()

    users_repo = make_user_repo_mock(user)
    with (
        patch("scheduler.jobs.NotificationService", return_value=notifications),
        patch("scheduler.jobs.UserRepo", return_value=users_repo),
    ):
        await _notify_payment_succeeded(bot, session=MagicMock(), payment=payment)

    assert bot.send_message.await_count == 2

    lang = user.language_code or "ru"
    price = format_price(payment.amount, payment.currency)
    expected_payment_text = t("payment.succeeded.message", lang, price=price)
    expected_menu_text = t("main.menu.title", lang)

    first_call = bot.send_message.await_args_list[0]
    second_call = bot.send_message.await_args_list[1]

    assert first_call.kwargs["chat_id"] == user.telegram_id
    assert first_call.kwargs["text"] == expected_payment_text

    assert second_call.kwargs["chat_id"] == user.telegram_id
    assert second_call.kwargs["text"] == expected_menu_text
    assert second_call.kwargs["reply_markup"] == main_menu_kb(user)

    notifications.log_success.assert_awaited_once()
    notifications.log_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_payment_succeeded_first_message_fails() -> None:
    user = make_user()
    payment = make_payment(user)
    bot = AsyncMock()
    bot.send_message.side_effect = Exception("telegram api error")
    notifications = make_notifications_mock()

    users_repo = make_user_repo_mock(user)
    with (
        patch("scheduler.jobs.NotificationService", return_value=notifications),
        patch("scheduler.jobs.UserRepo", return_value=users_repo),
    ):
        await _notify_payment_succeeded(bot, session=MagicMock(), payment=payment)

    bot.send_message.assert_called_once()
    notifications.log_failure.assert_awaited_once()
    notifications.log_success.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_payment_succeeded_second_message_fails() -> None:
    user = make_user()
    payment = make_payment(user)
    bot = AsyncMock()
    bot.send_message.side_effect = [None, Exception("menu send failed")]
    notifications = make_notifications_mock()

    users_repo = make_user_repo_mock(user)
    with (
        patch("scheduler.jobs.NotificationService", return_value=notifications),
        patch("scheduler.jobs.UserRepo", return_value=users_repo),
    ):
        await _notify_payment_succeeded(bot, session=MagicMock(), payment=payment)

    assert bot.send_message.await_count == 2
    notifications.log_success.assert_awaited_once()
    notifications.log_failure.assert_not_awaited()
