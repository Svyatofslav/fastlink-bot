from __future__ import annotations

import itertools
import random
import string
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from database.enums import (
    NotificationDeliveryStatus,
    NotificationType,
    PaymentProvider,
    PaymentStatus,
    RefundRequestStatus,
    RefundStatus,
)
from database.models import (
    NotificationLog,
    Payment,
    Refund,
    RefundRequest,
    User,
)
from services.notifications import NotificationService
from services.refund import RefundService

_property_test_counter = itertools.count(1)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_process_refund_result_idempotent(db_session: AsyncSession) -> None:
    """
    Дважды обрабатываем одно и то же refund.succeeded по provider_refund_id
    и проверяем:
    - Payment.refunded_amount не увеличивается повторно;
    - Payment.status остаётся REFUNDED_*;
    - в NotificationLog ровно одна запись REFUND_PROCESSED.
    """
    refund_service = RefundService(db_session)
    notification_service = NotificationService(db_session)

    # 0. Создаём пользователя и платёж без подписки (subscription_id=None)
    user = User(
        telegram_id=999_888_777,
        username="refunduser",
        first_name="Refund",
        last_name="User",
        language_code="ru",
        is_banned=False,
        is_active=True,
        last_active_at=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    payment = Payment(
        user_id=user.id,
        subscription_id=None,
        provider=PaymentProvider.YOOKASSA,
        provider_payment_id="pay-refund-1",
        amount=1000,
        currency="RUB",
        status=PaymentStatus.SUCCEEDED,
        idempotence_key="idem-refund-1",
        metadata_snapshot=None,
        paid_at=datetime.now(UTC),
        refundable=True,
        refunded_amount=0,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.refunded_amount == 0
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.subscription_id is None

    # 1. Заявка на возврат (без привязки к подписке)
    refund_request = RefundRequest(
        user_id=user.id,
        payment_id=payment.id,
        subscription_id=None,
        reason="test refund",
        status=RefundRequestStatus.APPROVED,
        admin_comment=None,
        reviewed_by_admin_id=None,
        reviewed_at=None,
    )
    db_session.add(refund_request)
    await db_session.commit()
    await db_session.refresh(refund_request)

    # 2. Создаём Refund по заявке через сервис
    refund: Refund = await refund_service.create_refund_for_request(
        refund_request_id=refund_request.id,
        amount=500,
        currency="RUB",
        provider_refund_id="ref-1",
        raw_payload={"test": "payload"},
    )
    await db_session.commit()
    await db_session.refresh(refund)

    assert refund.status == RefundStatus.PENDING
    await db_session.refresh(payment)
    assert payment.refunded_amount == 0

    # 3. Первый вызов process_refund_result с SUCCEEDED
    refund_1 = await refund_service.process_refund_result(
        provider_refund_id="ref-1",
        status=RefundStatus.SUCCEEDED,
        raw_payload={"test": "payload-1"},
    )
    await db_session.commit()
    await db_session.refresh(refund_1)
    await db_session.refresh(payment)

    # Payment.refunded_amount увеличивается на refund.amount
    assert payment.refunded_amount == refund.amount
    assert payment.status in (
        PaymentStatus.REFUNDED_PARTIALLY,
        PaymentStatus.REFUNDED_FULLY,
    )

    # Эмулируем реальную отправку уведомления о завершённой обработке рефанда
    if await notification_service.notify_refund_processed(
        user_id=payment.user_id,
        subscription_id=payment.subscription_id,
    ):
        await notification_service.log_success(
            user_id=payment.user_id,
            notification_type=NotificationType.REFUND_PROCESSED,
            subscription_id=payment.subscription_id,
            payload={"refund_id": refund_1.id},
        )
    await db_session.commit()

    refunded_amount_after_first = payment.refunded_amount
    status_after_first = payment.status

    # 4. Второй вызов process_refund_result с тем же provider_refund_id и SUCCEEDED
    refund_2 = await refund_service.process_refund_result(
        provider_refund_id="ref-1",
        status=RefundStatus.SUCCEEDED,
        raw_payload={"test": "payload-2"},
    )
    await db_session.commit()
    await db_session.refresh(refund_2)
    await db_session.refresh(payment)

    # SUM не меняется, статус остаётся таким же
    assert payment.refunded_amount == refunded_amount_after_first
    assert payment.status == status_after_first

    # notify_refund_processed должен вернуть False (дедупликация),
    # поэтому второе уведомление не логируем.
    should_notify_again = await notification_service.notify_refund_processed(
        user_id=payment.user_id,
        subscription_id=payment.subscription_id,
    )
    assert should_notify_again is False

    # 5. В NotificationLog ровно одна запись REFUND_PROCESSED
    result = await db_session.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == payment.user_id,
            NotificationLog.type == NotificationType.REFUND_PROCESSED,
        )
    )
    notifications_for_user = list(result.scalars().all())
    assert len(notifications_for_user) == 1

    log = notifications_for_user[0]
    assert log.delivery_status == NotificationDeliveryStatus.SENT
    assert log.subscription_id == payment.subscription_id


from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


@given(
    telegram_id=st.integers(min_value=1, max_value=10_000_000),
    amount=st.integers(min_value=100, max_value=1_000_000),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_process_refund_result_idempotent_property_based(
    db_session: AsyncSession,
    telegram_id: int,
    amount: int,
) -> None:
    """
    Property-тест: process_refund_result идемпотентен для ЛЮБЫХ данных.

    Проверяет:
    - При повторном вызове с тем же provider_refund_id refunded_amount не меняется
    - Payment.status не переписывается
    - NotificationLog не дублируется
    """
    refund_service = RefundService(db_session)

    unique_id = next(_property_test_counter)
    unique_telegram_id = telegram_id * 1000 + unique_id
    provider_refund_id = f"ref-{unique_id}-{''.join(random.choices(string.ascii_letters + string.digits, k=8))}"  # noqa: S311

    # 0. Создаём пользователя и платёж
    user = User(
        telegram_id=unique_telegram_id,
        username=f"user_{unique_telegram_id}",
        first_name="Refund",
        last_name="User",
        language_code="ru",
        is_banned=False,
        is_active=True,
        last_active_at=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    payment = Payment(
        user_id=user.id,
        subscription_id=None,
        provider=PaymentProvider.YOOKASSA,
        provider_payment_id=f"pay-{unique_telegram_id}",
        amount=amount,
        currency="RUB",
        status=PaymentStatus.SUCCEEDED,
        idempotence_key=f"idem-refund-{unique_telegram_id}",
        metadata_snapshot=None,
        paid_at=datetime.now(UTC),
        refundable=True,
        refunded_amount=0,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    # 1. Заявка на возврат
    refund_request = RefundRequest(
        user_id=user.id,
        payment_id=payment.id,
        subscription_id=None,
        reason="test refund",
        status=RefundRequestStatus.APPROVED,
        admin_comment=None,
        reviewed_by_admin_id=None,
        reviewed_at=None,
    )
    db_session.add(refund_request)
    await db_session.commit()
    await db_session.refresh(refund_request)

    # 2. Создаём Refund
    refund = await refund_service.create_refund_for_request(
        refund_request_id=refund_request.id,
        amount=amount // 2,
        currency="RUB",
        provider_refund_id=provider_refund_id,
        raw_payload={"test": "payload"},
    )
    await db_session.commit()
    await db_session.refresh(refund)

    # 3. Первый вызов process_refund_result
    refund_1 = await refund_service.process_refund_result(
        provider_refund_id=provider_refund_id,
        status=RefundStatus.SUCCEEDED,
        raw_payload={"test": "payload-1"},
    )
    await db_session.commit()
    await db_session.refresh(refund_1)
    await db_session.refresh(payment)

    refunded_amount_after_first = payment.refunded_amount
    status_after_first = payment.status

    # 4. Второй вызов process_refund_result с тем же provider_refund_id
    refund_2 = await refund_service.process_refund_result(
        provider_refund_id=provider_refund_id,
        status=RefundStatus.SUCCEEDED,
        raw_payload={"test": "payload-2"},
    )
    await db_session.commit()
    await db_session.refresh(refund_2)
    await db_session.refresh(payment)

    assert payment.refunded_amount == refunded_amount_after_first
    assert payment.status == status_after_first

    # 5. В NotificationLog ровно одна запись
    result = await db_session.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == payment.user_id,
            NotificationLog.type == NotificationType.REFUND_PROCESSED,
        )
    )
    notifications = list(result.scalars().all())
    assert len(notifications) == 1
