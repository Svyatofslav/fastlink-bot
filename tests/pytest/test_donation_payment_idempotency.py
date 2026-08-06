from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from database.enums import PaymentProvider
from database.models import User
from domain.donation_metadata import build_donation_metadata
from services.payment import PaymentService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_user(db_session: AsyncSession, telegram_id: int) -> User:
    user = User(
        telegram_id=telegram_id,
        username="donor2",
        first_name="Test",
        last_name="Donor2",
        language_code="ru",
        is_banned=False,
        is_active=True,
        last_active_at=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_donation_duplicate_idempotency_key_returns_same_payment(
    db_session: AsyncSession,
) -> None:
    """
    Повторный create_payment с тем же idempotency_key должен вернуть
    уже существующий Payment вместо падения на unique constraint —
    защищает от дублирования доната при повторной отправке формы,
    не показывая пользователю ошибку.
    """
    user = await _make_user(db_session, telegram_id=800_000_001)
    payment_service = PaymentService(db_session)
    metadata_snapshot = build_donation_metadata(user=user, amount=10000, currency="RUB")

    first_payment = await payment_service.create_payment(
        user_id=user.id,
        amount=10000,
        currency="RUB",
        provider=PaymentProvider.YOOKASSA,
        subscription_id=None,
        idempotency_key="donation-dup-key",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()

    second_payment = await payment_service.create_payment(
        user_id=user.id,
        amount=10000,
        currency="RUB",
        provider=PaymentProvider.YOOKASSA,
        subscription_id=None,
        idempotency_key="donation-dup-key",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()

    assert second_payment.id == first_payment.id


@pytest.mark.asyncio
async def test_donation_payment_created_without_subscription(
    db_session: AsyncSession,
) -> None:
    """
    Донат создаётся с subscription_id=None и не ломает FK payments.subscription_id
    (ForeignKey допускает NULL, ondelete=SET NULL).
    """
    user = await _make_user(db_session, telegram_id=800_000_002)
    payment_service = PaymentService(db_session)
    metadata_snapshot = build_donation_metadata(user=user, amount=15000, currency="RUB")

    payment = await payment_service.create_payment(
        user_id=user.id,
        amount=15000,
        currency="RUB",
        provider=PaymentProvider.YOOKASSA,
        subscription_id=None,
        idempotency_key="donation-no-sub",
        metadata_snapshot=metadata_snapshot,
    )
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.subscription_id is None
    assert payment.user_id == user.id
    assert payment.confirmation_url is not None
    assert payment.metadata_snapshot["type"] == "donation"
