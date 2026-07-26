from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_test_engine
from database.enums import PaymentProvider
from database.repo.refunds import RefundRepo
from database.repo.refund_requests import RefundRequestRepo
from database.repo.users import UserRepo
from database.enums import RefundRequestStatus
from domain.donation_metadata import build_donation_metadata
from services.payment import PaymentService
from services.refund import RefundService


@pytest_asyncio.fixture
async def concurrent_session_factory():
    engine = create_test_engine(pool_size=5)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _approve_refund(factory, refund_request_id: int, amount: int):
    """
    RefundService.create_refund_for_request идемпотентен по
    refund_request_id: при гонке (два админа одновременно одобрили одну
    и ту же заявку) второй вызов должен получить уже созданный Refund,
    а не создать дубликат.
    """
    async with factory() as session:
        service = RefundService(session)
        refund = await service.create_refund_for_request(
            refund_request_id=refund_request_id,
            amount=amount,
            currency="RUB",
        )
        await session.commit()
        return refund


@pytest.mark.asyncio
async def test_concurrent_refund_approval_creates_only_one_refund(
    concurrent_session_factory,
):
    async with concurrent_session_factory() as setup_session:
        user = await UserRepo(setup_session).create(
            telegram_id=999_000_222,
            username="refund_race_user",
        )
        await setup_session.commit()

        payment_service = PaymentService(setup_session)
        metadata = build_donation_metadata(user=user, amount=10000, currency="RUB")
        payment = await payment_service.create_payment(
            user_id=user.id,
            amount=10000,
            currency="RUB",
            provider=PaymentProvider.YOOKASSA,
            subscription_id=None,
            idempotency_key="refund-race-payment-key",
            metadata_snapshot=metadata,
        )
        await setup_session.commit()

        refund_request = await RefundRequestRepo(setup_session).create(
            user_id=user.id,
            payment_id=payment.id,
            subscription_id=None,
            reason="race condition test",
            status=RefundRequestStatus.APPROVED,
            admin_comment=None,
            reviewed_by_admin_id=None,
            reviewed_at=None,
        )
        await setup_session.commit()
        refund_request_id = refund_request.id
        payment_amount = payment.amount

    results = await asyncio.gather(
        _approve_refund(concurrent_session_factory, refund_request_id, payment_amount),
        _approve_refund(concurrent_session_factory, refund_request_id, payment_amount),
    )

    assert all(r is not None for r in results), (
        "RefundService.create_refund_for_request должен вернуть Refund "
        "в обоих случаях, даже при гонке двух одновременных одобрений."
    )

    ids = {r.id for r in results}
    assert len(ids) == 1, (
        "Оба параллельных одобрения одной и той же RefundRequest должны "
        "вернуть один и тот же Refund.id — гонка не должна приводить "
        "к появлению двух разных записей."
    )

    async with concurrent_session_factory() as check_session:
        refunds_in_db = await RefundRepo(check_session).get_by_refund_request(
            refund_request_id
        )
        assert len(refunds_in_db) == 1, (
            "В БД должна остаться ровно одна запись Refund для этой "
            "RefundRequest — гонка не должна приводить к дублированию."
        )
