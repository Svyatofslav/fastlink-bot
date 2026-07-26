from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_test_engine
from database.enums import NotificationType
from database.models import Server, Subscription, Tariff, User
from database.repo.notifications import NotificationRepo
from database.enums import SubscriptionStatus
from services.notifications import NotificationService


@pytest_asyncio.fixture
async def concurrent_session_factory():
    engine = create_test_engine(pool_size=5)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _notify_traffic_80(factory, user_id: int, subscription_id: int):
    """
    NotificationService._try_notify (используется notify_traffic_80 и
    остальными notify_* методами) идемпотентен по (user_id,
    subscription_id, type): при гонке двух параллельных обработчиков
    одного события (например, два воркера одновременно обрабатывают
    один и тот же трафик-чек) второй вызов должен тихо получить False,
    а не создать дубликат NotificationLog.
    """
    async with factory() as session:
        service = NotificationService(session)
        sent = await service.notify_traffic_80(
            user_id=user_id,
            subscription_id=subscription_id,
        )
        await session.commit()
        return sent


@pytest.mark.asyncio
async def test_concurrent_notify_traffic_80_sends_only_once(
    concurrent_session_factory,
):
    async with concurrent_session_factory() as setup_session:
        user = User(
            telegram_id=999_000_444,
            username="notify_race_user",
            first_name="Notify",
            last_name="Race",
            language_code="ru",
        )
        server = Server(
            name="notify-race-server",
            country_code=None,
            country_name=None,
            emoji=None,
            marzban_node_id=1,
            metrics_url=None,
            metrics_token=None,
            inbound_tag="notify-race-inbound",
            is_active=True,
            sort_order=100,
        )
        setup_session.add_all([user, server])
        await setup_session.flush()

        tariff = Tariff(
            server_id=None,
            name="Notify race tariff",
            duration_days=30,
            data_limit_bytes=1_000_000,
            price_amount=10000,
            price_currency="RUB",
            is_active=True,
            sort_order=100,
            description=None,
        )
        setup_session.add(tariff)
        await setup_session.flush()

        subscription = Subscription(
            user_id=user.id,
            server_id=server.id,
            tariff_id=tariff.id,
            marzban_username="notify-race-user",
            status=SubscriptionStatus.ACTIVE,
            starts_at=None,
            expires_at=None,
            data_limit_bytes=tariff.data_limit_bytes,
            data_used_bytes=0,
            auto_renew=False,
            subscription_url="https://example.com/sub/notify-race-user",
            disabled_reason=None,
        )
        setup_session.add(subscription)
        await setup_session.commit()

        user_id = user.id
        subscription_id = subscription.id

    results = await asyncio.gather(
        _notify_traffic_80(concurrent_session_factory, user_id, subscription_id),
        _notify_traffic_80(concurrent_session_factory, user_id, subscription_id),
    )

    assert sum(1 for r in results if r is True) == 1, (
        "Ровно один из двух параллельных вызовов notify_traffic_80 "
        "должен реально отправить уведомление (True); второй должен "
        "получить False из-за IntegrityError по uq_notifications_dedup."
    )

    async with concurrent_session_factory() as check_session:
        logs = await NotificationRepo(check_session).get_by_user(user_id)
        matching = [
            log
            for log in logs
            if log.type == NotificationType.TRAFFIC_80
            and log.subscription_id == subscription_id
        ]
        assert len(matching) == 1, (
            "В БД должна остаться ровно одна запись NotificationLog "
            "(user_id, subscription_id, TRAFFIC_80) — гонка не должна "
            "приводить к дублированию и повторной отправке пользователю."
        )
