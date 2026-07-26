from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import (
    PaymentProvider,
    PaymentStatus,
    RefundRequestStatus,
    RefundStatus,
)
from database.models import Payment, Refund, RefundRequest, User
from database.repo.refunds import RefundRepo
from services.refund import RefundAmountExceedsPaymentError, RefundService


async def _make_user(db_session: AsyncSession, telegram_id: int) -> User:
    user = User(
        telegram_id=telegram_id,
        username="refund_user",
        first_name="Test",
        last_name="Refund",
        language_code="ru",
        is_banned=False,
        is_active=True,
        last_active_at=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_payment(
    db_session: AsyncSession,
    user: User,
    amount: int,
    idempotence_key: str,
    refunded_amount: int = 0,
    status: PaymentStatus = PaymentStatus.SUCCEEDED,
) -> Payment:
    payment = Payment(
        user_id=user.id,
        subscription_id=None,
        provider=PaymentProvider.YOOKASSA,
        provider_payment_id=f"yk-{idempotence_key}",
        confirmation_url="https://example.com/pay",
        amount=amount,
        currency="RUB",
        status=status,
        idempotence_key=idempotence_key,
        metadata_snapshot={"type": "test"},
        paid_at=datetime.now(timezone.utc),
        refundable=True,
        refunded_amount=refunded_amount,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


async def _make_refund_request(
    db_session: AsyncSession, user: User, payment: Payment
) -> RefundRequest:
    refund_request = RefundRequest(
        user_id=user.id,
        payment_id=payment.id,
        subscription_id=None,
        reason="test reason",
        status=RefundRequestStatus.APPROVED,
        admin_comment=None,
        reviewed_by_admin_id=None,
        reviewed_at=None,
    )
    db_session.add(refund_request)
    await db_session.commit()
    await db_session.refresh(refund_request)
    return refund_request


@pytest.mark.asyncio
async def test_refund_amount_exceeds_available_raises(db_session: AsyncSession) -> None:
    """
    Одобрение рефанда на сумму больше стоимости платежа должно быть
    заблокировано до вставки в БД — деньги не должны уйти сверх лимита.
    """
    user = await _make_user(db_session, telegram_id=810_000_001)
    payment = await _make_payment(
        db_session, user, amount=10000, idempotence_key="refund-val-1"
    )
    refund_request = await _make_refund_request(db_session, user, payment)

    refund_service = RefundService(db_session)

    with pytest.raises(RefundAmountExceedsPaymentError) as exc_info:
        await refund_service.create_refund_for_request(
            refund_request_id=refund_request.id,
            amount=15000,
            currency="RUB",
        )

    assert exc_info.value.payment_id == payment.id
    assert exc_info.value.requested == 15000
    assert exc_info.value.available == 10000

    refunds_in_db = await RefundRepo(db_session).get_by_refund_request(
        refund_request.id
    )
    assert refunds_in_db == []


@pytest.mark.asyncio
async def test_refund_amount_accumulation_blocks_second_partial_refund(
    db_session: AsyncSession,
) -> None:
    """
    Два одобренных частичных рефанда по одному и тому же платежу не должны
    суммарно превысить payment.amount — второй запрос должен быть отклонён,
    даже если по отдельности каждая сумма меньше стоимости платежа.
    """
    user = await _make_user(db_session, telegram_id=810_000_002)
    payment = await _make_payment(
        db_session, user, amount=10000, idempotence_key="refund-val-2"
    )

    refund_service = RefundService(db_session)

    first_request = await _make_refund_request(db_session, user, payment)
    first_refund = await refund_service.create_refund_for_request(
        refund_request_id=first_request.id,
        amount=6000,
        currency="RUB",
    )
    await db_session.commit()
    assert first_refund.amount == 6000

    second_request = await _make_refund_request(db_session, user, payment)

    with pytest.raises(RefundAmountExceedsPaymentError) as exc_info:
        await refund_service.create_refund_for_request(
            refund_request_id=second_request.id,
            amount=6000,
            currency="RUB",
        )

    assert exc_info.value.available == 4000

    third_refund = await refund_service.create_refund_for_request(
        refund_request_id=second_request.id,
        amount=4000,
        currency="RUB",
    )
    await db_session.commit()
    assert third_refund.amount == 4000


@pytest.mark.asyncio
async def test_refund_amount_zero_or_negative_rejected(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, telegram_id=810_000_003)
    payment = await _make_payment(
        db_session, user, amount=10000, idempotence_key="refund-val-3"
    )
    refund_request = await _make_refund_request(db_session, user, payment)

    refund_service = RefundService(db_session)

    with pytest.raises(ValueError):
        await refund_service.create_refund_for_request(
            refund_request_id=refund_request.id,
            amount=0,
            currency="RUB",
        )

    with pytest.raises(ValueError):
        await refund_service.create_refund_for_request(
            refund_request_id=refund_request.id,
            amount=-100,
            currency="RUB",
        )


@pytest.mark.asyncio
async def test_process_refund_result_defensive_check_marks_failed(
    db_session: AsyncSession,
) -> None:
    """
    Симулирует аномальный сценарий, минуя create_refund_for_request:
    Refund с суммой, которая в сумме с уже накопленным refunded_amount
    превысит payment.amount. process_refund_result должен пометить такой
    Refund как FAILED и не трогать Payment.refunded_amount/status.
    """
    user = await _make_user(db_session, telegram_id=810_000_004)
    payment = await _make_payment(
        db_session,
        user,
        amount=10000,
        idempotence_key="refund-val-4",
        refunded_amount=6000,
        status=PaymentStatus.REFUNDED_PARTIALLY,
    )

    refund_request = await _make_refund_request(db_session, user, payment)

    rogue_refund = Refund(
        payment_id=payment.id,
        refund_request_id=refund_request.id,
        provider=PaymentProvider.YOOKASSA,
        provider_refund_id="yk-refund-rogue-1",
        amount=5000,
        currency="RUB",
        status=RefundStatus.PENDING,
        raw_payload=None,
        completed_at=None,
    )
    db_session.add(rogue_refund)
    await db_session.commit()
    await db_session.refresh(rogue_refund)

    refund_service = RefundService(db_session)

    result = await refund_service.process_refund_result(
        provider_refund_id="yk-refund-rogue-1",
        status=RefundStatus.SUCCEEDED,
        raw_payload={"anomaly": "amount_mismatch"},
    )
    await db_session.commit()

    assert result.status == RefundStatus.FAILED

    await db_session.refresh(payment)
    assert payment.refunded_amount == 6000
    assert payment.status == PaymentStatus.REFUNDED_PARTIALLY
