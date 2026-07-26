from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import (
    PaymentProvider,
    PaymentStatus,
    NotificationType,
    NotificationDeliveryStatus,
)
from database.models import User, NotificationLog
from services.notifications import NotificationService
from services.payment import PaymentService


@pytest.mark.asyncio
async def test_process_successful_payment_idempotent(db_session: AsyncSession) -> None:
    """
    Дважды обрабатываем одно и то же payment.succeeded по provider_payment_id
    и проверяем:
    - статус платежа остаётся SUCCEEDED;
    - paid_at не меняется после первого вызова;
    - в NotificationLog ровно одна запись PAYMENT_SUCCEEDED.
    """
    payment_service = PaymentService(db_session)
    notification_service = NotificationService(db_session)

    # 0. Создаём пользователя, чтобы не нарушать FK payments.user_id → users.id
    user = User(
        telegram_id=111_222_333,
        username="testuser",
        first_name="Test",
        last_name="User",
        language_code="ru",
        is_banned=False,
        is_active=True,
        last_active_at=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    user_id = user.id

    # 1. Создаём Payment через реальный сервис
    payment = await payment_service.create_payment(
        user_id=user_id,
        amount=1000,
        currency="RUB",
        provider=PaymentProvider.YOOKASSA,
        subscription_id=None,
        idempotency_key="idem-1",
        metadata_snapshot=None,
    )
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.provider_payment_id is not None
    assert payment.confirmation_url is not None

    # 2. Привязываем provider_payment_id, как после инициализации у провайдера
    payment = await payment_service.attach_provider_payment_id(
        payment_id=payment.id,
        provider_payment_id="pay-1",
    )
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.provider_payment_id == "pay-1"

    # 3. Первый вызов process_successful_payment
    paid_at_1 = datetime.now(timezone.utc)
    payment_1 = await payment_service.process_successful_payment(
        provider_payment_id="pay-1",
        paid_at=paid_at_1,
        subscription_id=None,
        metadata_snapshot={"test": "snapshot"},
        new_subscription_params=None,
    )
    await db_session.commit()
    await db_session.refresh(payment_1)

    assert payment_1.status == PaymentStatus.SUCCEEDED
    assert payment_1.paid_at is not None
    first_paid_at = payment_1.paid_at

    # Эмулируем реальную отправку уведомления:
    first_notify_sent = await notification_service.notify_payment_succeeded(
        user_id=user_id,
        subscription_id=payment_1.subscription_id,
    )
    assert first_notify_sent is True
    await db_session.commit()

    # 4. Второй вызов process_successful_payment с тем же provider_payment_id
    paid_at_2 = datetime.now(timezone.utc)
    payment_2 = await payment_service.process_successful_payment(
        provider_payment_id="pay-1",
        paid_at=paid_at_2,
        subscription_id=None,
        metadata_snapshot={"test": "snapshot-2"},
        new_subscription_params=None,
    )
    await db_session.commit()
    await db_session.refresh(payment_2)

    # Статус не меняется (остаётся SUCCEEDED), paid_at не переписывается
    assert payment_2.status == PaymentStatus.SUCCEEDED
    assert payment_2.paid_at == first_paid_at

    # Эмулируем второй заход webhook-а:
    should_notify_again = await notification_service.notify_payment_succeeded(
        user_id=user_id,
        subscription_id=payment_2.subscription_id,
    )
    assert should_notify_again is False

    # 5. Проверяем, что NotificationLog содержит ровно одну запись PAYMENT_SUCCEEDED
    result = await db_session.execute(
        select(NotificationLog).where(
            NotificationLog.user_id == user_id,
            NotificationLog.type == NotificationType.PAYMENT_SUCCEEDED,
        )
    )
    notifications_for_user = list(result.scalars().all())
    assert len(notifications_for_user) == 1

    log = notifications_for_user[0]
    assert log.delivery_status == NotificationDeliveryStatus.SENT
    assert log.subscription_id == payment_2.subscription_id
