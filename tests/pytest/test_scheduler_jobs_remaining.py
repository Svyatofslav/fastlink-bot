from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database.enums import DisabledReason
from scheduler.jobs import (
    _ensure_subscription_activated,
    _notify_payment_succeeded,
    _parse_datetime,
    expire_overdue_subscriptions,
    notify_donation_succeeded,
    process_webhook_events,
    send_expiration_reminders_1d,
    send_expiration_reminders_3d,
)


def make_user(telegram_id: int = 123456, language_code: str = "ru") -> SimpleNamespace:
    return SimpleNamespace(id=1, telegram_id=telegram_id, language_code=language_code)


def make_payment(
    user: SimpleNamespace, amount: int = 29900, currency: str = "RUB"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=10, user_id=user.id, subscription_id=None, amount=amount, currency=currency
    )


class _FakeSessionCM:
    """Имитирует `async with factory() as session: ...` без реальной БД."""

    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *exc: object) -> bool:
        return False


def factory_for(session: MagicMock):
    def factory():
        return _FakeSessionCM(session)

    return factory


def make_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------


def test_parse_datetime_none_for_empty_or_none() -> None:
    assert _parse_datetime(None) is None
    assert _parse_datetime("") is None


def test_parse_datetime_valid_iso_string() -> None:
    result = _parse_datetime("2026-09-01T00:00:00+00:00")
    assert result == datetime(2026, 9, 1, tzinfo=UTC)


def test_parse_datetime_invalid_string_returns_none() -> None:
    assert _parse_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# process_webhook_events — тонкая обёртка над process_webhook_events_with_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_webhook_events_opens_session_and_delegates() -> None:
    session = make_session()

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch(
            "scheduler.jobs.process_webhook_events_with_session", new=AsyncMock()
        ) as delegate,
    ):
        await process_webhook_events(provider="yookassa", limit=42, bot=None)

    delegate.assert_awaited_once_with(
        session=session, provider="yookassa", limit=42, bot=None
    )


# ---------------------------------------------------------------------------
# _notify_payment_succeeded — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_payment_succeeded_no_bot_skips_entirely() -> None:
    payment = make_payment(make_user())

    with patch("scheduler.jobs.NotificationService") as notif_cls:
        await _notify_payment_succeeded(None, session=MagicMock(), payment=payment)

    notif_cls.assert_not_called()


@pytest.mark.asyncio
async def test_notify_payment_succeeded_dedup_skips_send() -> None:
    payment = make_payment(make_user())
    bot = AsyncMock()
    notifications = MagicMock()
    notifications.should_send = AsyncMock(return_value=False)

    with patch("scheduler.jobs.NotificationService", return_value=notifications):
        await _notify_payment_succeeded(bot, session=MagicMock(), payment=payment)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_payment_succeeded_no_user_returns() -> None:
    payment = make_payment(make_user())
    bot = AsyncMock()
    notifications = MagicMock()
    notifications.should_send = AsyncMock(return_value=True)
    users_repo = MagicMock()
    users_repo.get_by_id = AsyncMock(return_value=None)

    with (
        patch("scheduler.jobs.NotificationService", return_value=notifications),
        patch("scheduler.jobs.UserRepo", return_value=users_repo),
    ):
        await _notify_payment_succeeded(bot, session=MagicMock(), payment=payment)

    bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# notify_donation_succeeded — недостающие ветки (аналог _notify_payment_succeeded)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_donation_succeeded_no_bot_skips_entirely() -> None:
    payment = make_payment(make_user())

    with patch("scheduler.jobs.NotificationService") as notif_cls:
        await notify_donation_succeeded(None, session=MagicMock(), payment=payment)

    notif_cls.assert_not_called()


@pytest.mark.asyncio
async def test_notify_donation_succeeded_no_user_returns() -> None:
    payment = make_payment(make_user())
    bot = AsyncMock()
    notifications = MagicMock()
    notifications.should_send = AsyncMock(return_value=True)
    users_repo = MagicMock()
    users_repo.get_by_id = AsyncMock(return_value=None)

    with (
        patch("scheduler.jobs.NotificationService", return_value=notifications),
        patch("scheduler.jobs.UserRepo", return_value=users_repo),
    ):
        await notify_donation_succeeded(bot, session=MagicMock(), payment=payment)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_donation_succeeded_send_fails_logs_failure() -> None:
    user = make_user()
    payment = make_payment(user)
    bot = AsyncMock()
    bot.send_message.side_effect = Exception("telegram api error")
    notifications = MagicMock()
    notifications.should_send = AsyncMock(return_value=True)
    notifications.log_failure = AsyncMock()
    notifications.log_success = AsyncMock()
    users_repo = MagicMock()
    users_repo.get_by_id = AsyncMock(return_value=user)

    with (
        patch("scheduler.jobs.NotificationService", return_value=notifications),
        patch("scheduler.jobs.UserRepo", return_value=users_repo),
    ):
        await notify_donation_succeeded(bot, session=MagicMock(), payment=payment)

    notifications.log_failure.assert_awaited_once()
    notifications.log_success.assert_not_awaited()


# ---------------------------------------------------------------------------
# _ensure_subscription_activated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_subscription_activated_not_found_returns() -> None:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=None)
    marzban_service = MagicMock()
    marzban_service.activate_subscription = AsyncMock()

    with (
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch(
            "scheduler.jobs.SubscriptionMarzbanService", return_value=marzban_service
        ),
    ):
        await _ensure_subscription_activated(MagicMock(), subscription_id=123)

    marzban_service.activate_subscription.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_subscription_activated_already_activated_is_noop() -> None:
    subscription = SimpleNamespace(subscription_url="https://example.com/sub/x")
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=subscription)
    marzban_service = MagicMock()
    marzban_service.activate_subscription = AsyncMock()

    with (
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch(
            "scheduler.jobs.SubscriptionMarzbanService", return_value=marzban_service
        ),
    ):
        await _ensure_subscription_activated(MagicMock(), subscription_id=5)

    marzban_service.activate_subscription.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_subscription_activated_activates_when_pending() -> None:
    subscription = SimpleNamespace(subscription_url=None)
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=subscription)
    marzban_service = MagicMock()
    marzban_service.activate_subscription = AsyncMock()

    with (
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch(
            "scheduler.jobs.SubscriptionMarzbanService", return_value=marzban_service
        ),
    ):
        await _ensure_subscription_activated(MagicMock(), subscription_id=7)

    marzban_service.activate_subscription.assert_awaited_once_with(7)


# ---------------------------------------------------------------------------
# expire_overdue_subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expire_overdue_subscriptions_empty_list_returns_early() -> None:
    session = make_session()
    repo = MagicMock()
    repo.get_expired = AsyncMock(return_value=[])
    service = MagicMock()
    service.disable = AsyncMock()

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.SubscriptionService", return_value=service),
    ):
        await expire_overdue_subscriptions()

    service.disable.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_expire_overdue_subscriptions_disables_each_and_commits() -> None:
    session = make_session()
    subs = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    repo = MagicMock()
    repo.get_expired = AsyncMock(return_value=subs)
    service = MagicMock()
    service.disable = AsyncMock()

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.SubscriptionService", return_value=service),
    ):
        await expire_overdue_subscriptions()

    assert service.disable.await_count == 2
    service.disable.assert_any_await(
        subscription_id=1, disabled_reason=DisabledReason.EXPIRED, admin_id=None
    )
    service.disable.assert_any_await(
        subscription_id=2, disabled_reason=DisabledReason.EXPIRED, admin_id=None
    )
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_expire_overdue_subscriptions_one_failure_does_not_stop_batch() -> None:
    session = make_session()
    subs = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    repo = MagicMock()
    repo.get_expired = AsyncMock(return_value=subs)
    service = MagicMock()
    service.disable = AsyncMock(side_effect=[Exception("marzban down"), None])

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.SubscriptionService", return_value=service),
    ):
        await expire_overdue_subscriptions()

    assert service.disable.await_count == 2
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_expire_overdue_subscriptions_batch_failure_rolls_back() -> None:
    session = make_session()
    repo = MagicMock()
    repo.get_expired = AsyncMock(side_effect=Exception("db down"))
    service = MagicMock()
    service.disable = AsyncMock()

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.SubscriptionService", return_value=service),
    ):
        await expire_overdue_subscriptions()

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# _send_expiration_reminders (через send_expiration_reminders_3d/1d)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_expiration_reminders_empty_list_returns_early() -> None:
    session = make_session()
    repo = MagicMock()
    repo.get_expiring = AsyncMock(return_value=[])
    notifications = MagicMock()
    notifications.notify_sub_expires_3d = AsyncMock()

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.NotificationService", return_value=notifications),
    ):
        await send_expiration_reminders_3d()

    notifications.notify_sub_expires_3d.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_expiration_reminders_3d_calls_correct_method_per_subscription() -> (
    None
):
    session = make_session()
    subs = [
        SimpleNamespace(id=1, user_id=100),
        SimpleNamespace(id=2, user_id=200),
    ]
    repo = MagicMock()
    repo.get_expiring = AsyncMock(return_value=subs)
    notifications = MagicMock()
    notifications.notify_sub_expires_3d = AsyncMock(return_value=True)

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.NotificationService", return_value=notifications),
    ):
        await send_expiration_reminders_3d()

    assert notifications.notify_sub_expires_3d.await_count == 2
    notifications.notify_sub_expires_3d.assert_any_await(user_id=100, subscription_id=1)
    notifications.notify_sub_expires_3d.assert_any_await(user_id=200, subscription_id=2)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_expiration_reminders_1d_calls_correct_method() -> None:
    session = make_session()
    subs = [SimpleNamespace(id=1, user_id=100)]
    repo = MagicMock()
    repo.get_expiring = AsyncMock(return_value=subs)
    notifications = MagicMock()
    notifications.notify_sub_expires_1d = AsyncMock(return_value=True)
    notifications.notify_sub_expires_3d = AsyncMock()

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.NotificationService", return_value=notifications),
    ):
        await send_expiration_reminders_1d()

    notifications.notify_sub_expires_1d.assert_awaited_once_with(
        user_id=100, subscription_id=1
    )
    notifications.notify_sub_expires_3d.assert_not_awaited()
    repo.get_expiring.assert_awaited_once_with(within_days=1)


@pytest.mark.asyncio
async def test_send_expiration_reminders_one_failure_does_not_stop_batch() -> None:
    session = make_session()
    subs = [SimpleNamespace(id=1, user_id=100), SimpleNamespace(id=2, user_id=200)]
    repo = MagicMock()
    repo.get_expiring = AsyncMock(return_value=subs)
    notifications = MagicMock()
    notifications.notify_sub_expires_3d = AsyncMock(
        side_effect=[Exception("notify failed"), True]
    )

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.NotificationService", return_value=notifications),
    ):
        await send_expiration_reminders_3d()

    assert notifications.notify_sub_expires_3d.await_count == 2
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_expiration_reminders_batch_failure_rolls_back() -> None:
    session = make_session()
    repo = MagicMock()
    repo.get_expiring = AsyncMock(side_effect=Exception("db down"))
    notifications = MagicMock()

    with (
        patch(
            "scheduler.jobs.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("scheduler.jobs.SubscriptionRepo", return_value=repo),
        patch("scheduler.jobs.NotificationService", return_value=notifications),
    ):
        await send_expiration_reminders_3d()

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
