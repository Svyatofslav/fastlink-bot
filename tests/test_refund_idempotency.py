from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import (
    PaymentProvider,
    PaymentStatus,
    RefundRequestStatus,
    RefundStatus,
    NotificationType,
    NotificationDeliveryStatus,
)
from database.models import (
    User,
    Payment,
    RefundRequest,
    Refund,
    NotificationLog,
)
from services.notifications import NotificationService
from services.refund import RefundService


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
        paid_at=datetime.now(timezone.utc),
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
