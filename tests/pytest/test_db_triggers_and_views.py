from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_test_engine
from database.enums import (
    PaymentProvider,
    PaymentStatus,
    RefundRequestStatus,
    RefundStatus,
    SubscriptionStatus,
    WebhookEventStatus,
)
from database.models import (
    Payment,
    Refund,
    RefundRequest,
    Server,
    Subscription,
    Tariff,
    User,
    WebhookEvent,
)


@pytest_asyncio.fixture
async def plain_session_factory():
    """
    Фабрика сессий с реальными commit'ами (без SAVEPOINT/rollback),
    аналогично concurrent_session_factory из test_webhook_event_race.py.

    Нужна там, где важен факт РЕАЛЬНОГО commit'а между операциями —
    в частности, для проверки updated_at-триггера: now() в Postgres
    фиксируется на старте транзакции, поэтому INSERT и UPDATE в рамках
    db_session (единая открытая транзакция) дадут одинаковый updated_at.
    """
    engine = create_test_engine(pool_size=5)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _make_user(session) -> User:
    user = User(
        telegram_id=900_000_000 + id(session) % 100_000, username="trigger_test_user"
    )
    session.add(user)
    await session.flush()
    return user


async def _make_server(session) -> Server:
    server = Server(
        name="Trigger Test Server",
        country_name="Testland",
        inbound_tag="vless-test",
    )
    session.add(server)
    await session.flush()
    return server


async def _make_tariff(session, server: Server) -> Tariff:
    tariff = Tariff(
        server_id=server.id,
        name="Test Tariff",
        duration_days=30,
        data_limit_bytes=50_000_000_000,
        price_amount=19900,
    )
    session.add(tariff)
    await session.flush()
    return tariff


async def _make_subscription(
    session, user: User, server: Server, tariff: Tariff, status: SubscriptionStatus
) -> Subscription:
    sub = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username=f"user_{user.id}",
        status=status,
        data_limit_bytes=tariff.data_limit_bytes,
        subscription_url="https://example.com/sub/test",
    )
    session.add(sub)
    await session.flush()
    return sub


async def _make_payment(session, user: User, amount: int = 19900) -> Payment:
    payment = Payment(
        user_id=user.id,
        amount=amount,
        status=PaymentStatus.SUCCEEDED,
        idempotence_key=f"idem-{user.id}-{amount}",
        refundable=True,
    )
    session.add(payment)
    await session.flush()
    return payment


# --- updated_at trigger ---------------------------------------------------


@pytest.mark.asyncio
async def test_updated_at_trigger_updates_timestamp_on_row_update(
    plain_session_factory,
):
    async with plain_session_factory() as session:
        server = await _make_server(session)
        await session.commit()
        server_id = server.id
        created_at = server.created_at
        updated_at_initial = server.updated_at

    assert created_at == updated_at_initial, (
        "На момент INSERT created_at и updated_at должны совпадать "
        "(оба выставлены server_default now())."
    )

    # Гарантируем реальный сдвиг времени между двумя транзакциями,
    # так как Postgres now() фиксируется на старте каждой транзакции.
    await asyncio.sleep(1.05)

    async with plain_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM servers WHERE id = :id FOR UPDATE"),
            {"id": server_id},
        )
        assert result.scalar_one() == server_id

        await session.execute(
            text("UPDATE servers SET name = :name WHERE id = :id"),
            {"name": "Trigger Test Server (renamed)", "id": server_id},
        )
        await session.commit()

    async with plain_session_factory() as session:
        row = await session.execute(
            text("SELECT created_at, updated_at FROM servers WHERE id = :id"),
            {"id": server_id},
        )
        created_at_after, updated_at_after = row.one()

    assert created_at_after == created_at, (
        "created_at не должен меняться при UPDATE — триггер трогает только updated_at."
    )
    assert updated_at_after > updated_at_initial, (
        "Триггер set_updated_at() должен выставлять NEW.updated_at = "
        "now() при каждом UPDATE строки."
    )


@pytest.mark.asyncio
async def test_updated_at_trigger_fires_only_on_update_not_plain_select(
    plain_session_factory,
):
    async with plain_session_factory() as session:
        server = await _make_server(session)
        await session.commit()
        server_id = server.id
        updated_at_initial = server.updated_at

    await asyncio.sleep(1.05)

    async with plain_session_factory() as session:
        await session.execute(
            text("SELECT * FROM servers WHERE id = :id"), {"id": server_id}
        )
        # без UPDATE, только SELECT

    async with plain_session_factory() as session:
        row = await session.execute(
            text("SELECT updated_at FROM servers WHERE id = :id"),
            {"id": server_id},
        )
        updated_at_after = row.scalar_one()

    assert updated_at_after == updated_at_initial, (
        "SELECT не должен вызывать триггер и менять updated_at."
    )


# --- webhook_events_audit trigger -----------------------------------------


@pytest.mark.asyncio
async def test_webhook_events_audit_logs_insert(db_session):
    event = WebhookEvent(
        provider="yookassa",
        event_type="payment.succeeded",
        external_id="yk-audit-insert-1",
        status=WebhookEventStatus.RECEIVED,
        payload={"object": {"id": "yk-audit-insert-1"}},
    )
    db_session.add(event)
    await db_session.flush()

    rows = await db_session.execute(
        text(
            "SELECT operation, old_row, new_row FROM webhook_events_audit "
            "WHERE event_id = :event_id"
        ),
        {"event_id": event.id},
    )
    audit_rows = rows.all()

    assert len(audit_rows) == 1, (
        "AFTER INSERT триггер должен создать ровно одну audit-запись."
    )
    operation, old_row, new_row = audit_rows[0]
    assert operation == "INSERT"
    assert old_row is None, "Для INSERT old_row должен быть NULL."
    assert new_row["external_id"] == "yk-audit-insert-1"
    assert (
        new_row["status"] == "RECEIVED" or "received" in str(new_row["status"]).lower()
    )


@pytest.mark.asyncio
async def test_webhook_events_audit_logs_update_with_old_and_new_row(db_session):
    event = WebhookEvent(
        provider="yookassa",
        event_type="payment.succeeded",
        external_id="yk-audit-update-1",
        status=WebhookEventStatus.RECEIVED,
        payload={"object": {"id": "yk-audit-update-1"}},
    )
    db_session.add(event)
    await db_session.flush()

    event.status = WebhookEventStatus.PROCESSING
    await db_session.flush()

    rows = await db_session.execute(
        text(
            "SELECT operation, old_row, new_row FROM webhook_events_audit "
            "WHERE event_id = :event_id ORDER BY id"
        ),
        {"event_id": event.id},
    )
    audit_rows = rows.all()

    assert len(audit_rows) == 2, (
        "После INSERT + UPDATE должно быть две audit-записи: одна на каждую операцию."
    )

    insert_row, update_row = audit_rows
    assert insert_row.operation == "INSERT"
    assert update_row.operation == "UPDATE"
    assert update_row.old_row is not None, (
        "Для UPDATE old_row должен содержать снимок строки ДО изменения."
    )
    assert update_row.new_row is not None
    assert "RECEIVED" in str(update_row.old_row["status"]).upper()
    assert "PROCESSING" in str(update_row.new_row["status"]).upper()


# --- active_subscriptions_view ---------------------------------------------


@pytest.mark.asyncio
async def test_active_subscriptions_view_includes_active_subscription(db_session):
    user = await _make_user(db_session)
    server = await _make_server(db_session)
    tariff = await _make_tariff(db_session, server)
    sub = await _make_subscription(
        db_session, user, server, tariff, SubscriptionStatus.ACTIVE
    )

    row = await db_session.execute(
        text(
            "SELECT subscription_id, status, user_id, server_name, "
            "tariff_name, price_amount FROM active_subscriptions_view "
            "WHERE subscription_id = :id"
        ),
        {"id": sub.id},
    )
    result = row.one_or_none()

    assert result is not None, "Активная подписка должна попадать в view."
    assert result.status == "ACTIVE" or "ACTIVE" in str(result.status).upper()
    assert result.user_id == user.id
    assert result.server_name == "Trigger Test Server"
    assert result.tariff_name == "Test Tariff"
    assert result.price_amount == 19900


@pytest.mark.asyncio
async def test_active_subscriptions_view_excludes_non_active_subscription(db_session):
    user = await _make_user(db_session)
    server = await _make_server(db_session)
    tariff = await _make_tariff(db_session, server)
    sub = await _make_subscription(
        db_session, user, server, tariff, SubscriptionStatus.DISABLED
    )

    row = await db_session.execute(
        text(
            "SELECT subscription_id FROM active_subscriptions_view "
            "WHERE subscription_id = :id"
        ),
        {"id": sub.id},
    )
    result = row.one_or_none()

    assert result is None, (
        "View фильтрует по status = 'ACTIVE' — DISABLED-подписка не "
        "должна попадать в выборку."
    )


@pytest.mark.asyncio
async def test_active_subscriptions_view_left_joins_tariff_when_null(db_session):
    """
    tariff_id у Subscription nullable (ON DELETE SET NULL) — view должен
    отдавать строку с tariff_name = NULL через LEFT JOIN, а не терять
    подписку целиком.
    """
    user = await _make_user(db_session)
    server = await _make_server(db_session)

    sub = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=None,
        marzban_username=f"user_no_tariff_{user.id}",
        status=SubscriptionStatus.ACTIVE,
        data_limit_bytes=0,
        subscription_url="https://example.com/sub/no-tariff",
    )
    db_session.add(sub)
    await db_session.flush()

    row = await db_session.execute(
        text(
            "SELECT subscription_id, tariff_name FROM active_subscriptions_view "
            "WHERE subscription_id = :id"
        ),
        {"id": sub.id},
    )
    result = row.one_or_none()

    assert result is not None
    assert result.tariff_name is None


# --- payment_refund_overview_view ------------------------------------------


@pytest.mark.asyncio
async def test_payment_refund_overview_view_includes_refund_chain(db_session):
    user = await _make_user(db_session)
    payment = await _make_payment(db_session, user, amount=10000)

    refund_request = RefundRequest(
        user_id=user.id,
        payment_id=payment.id,
        reason="Не подошёл сервис",
        status=RefundRequestStatus.APPROVED,
    )
    db_session.add(refund_request)
    await db_session.flush()

    refund = Refund(
        payment_id=payment.id,
        refund_request_id=refund_request.id,
        provider=PaymentProvider.YOOKASSA,
        amount=10000,
        status=RefundStatus.SUCCEEDED,
    )
    db_session.add(refund)
    await db_session.flush()

    row = await db_session.execute(
        text(
            "SELECT payment_id, refund_request_status, refund_status, "
            "refund_amount FROM payment_refund_overview_view "
            "WHERE payment_id = :id"
        ),
        {"id": payment.id},
    )
    result = row.one_or_none()

    assert result is not None
    assert "APPROVED" in str(result.refund_request_status).upper()
    assert "SUCCEEDED" in str(result.refund_status).upper()
    assert result.refund_amount == 10000


@pytest.mark.asyncio
async def test_payment_refund_overview_view_left_joins_payment_without_refund(
    db_session,
):
    """
    Платёж без единого refund_request/refund всё равно должен попадать
    в view (через LEFT JOIN), с NULL в refund-полях, а не пропадать из
    выборки.
    """
    user = await _make_user(db_session)
    payment = await _make_payment(db_session, user, amount=5000)

    row = await db_session.execute(
        text(
            "SELECT payment_id, refund_request_id, refund_id, refund_amount "
            "FROM payment_refund_overview_view WHERE payment_id = :id"
        ),
        {"id": payment.id},
    )
    result = row.one_or_none()

    assert result is not None, (
        "Платёж без рефандов должен присутствовать в view через LEFT JOIN."
    )
    assert result.refund_request_id is None
    assert result.refund_id is None
    assert result.refund_amount is None
