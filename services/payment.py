from __future__ import annotations

import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import PaymentProvider, PaymentStatus
from database.models import Payment
from database.repo.payments import PaymentRepo
from services.notifications import NotificationService
from services.subscription import SubscriptionService

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class NewSubscriptionParams:
    """
    Параметры для создания новой подписки после успешного платежа.
    """

    tariff_id: int
    server_id: int
    marzban_username: str
    starts_at: datetime | None
    expires_at: datetime


class PaymentService:
    """
    Application-уровневый сервис для работы с платежами.

    Оркестрирует:
    - создание записи Payment перед обращением к провайдеру,
    - обработку событий от провайдера (успех/отмена),
    - привязку Payment к Subscription,
    - уведомления пользователя об успешном платеже.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._payments = PaymentRepo(session)
        self._notifications = NotificationService(session)
        self._subscriptions = SubscriptionService(session)

    async def create_payment(
        self,
        *,
        user_id: int,
        amount: int,
        currency: str,
        provider: PaymentProvider = PaymentProvider.YOOKASSA,
        subscription_id: int | None = None,
        idempotence_key: str,
        metadata_snapshot: dict[str, Any] | None = None,
    ) -> Payment:
        """
        Создать запись Payment в статусе PENDING.

        Предполагается, что после этого внешний код идёт к провайдеру
        и инициализирует платёж (получает provider_payment_id, ссылку и т.п.).
        """
        payment = await self._payments.create(
            user_id=user_id,
            subscription_id=subscription_id,
            provider=provider,
            provider_payment_id=None,
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,
            idempotence_key=idempotence_key,
            metadata_snapshot=metadata_snapshot,
            paid_at=None,
            refundable=False,
            refunded_amount=0,
        )
        return payment

    async def attach_provider_payment_id(
        self,
        *,
        payment_id: int,
        provider_payment_id: str,
    ) -> Payment:
        """
        Сохранить идентификатор платежа у провайдера (provider_payment_id)
        после успешной инициализации платежа.
        """
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found")

        payment = await self._payments.update(
            payment,
            provider_payment_id=provider_payment_id,
        )
        return payment

    async def process_successful_payment(
        self,
        *,
        provider_payment_id: str,
        paid_at: datetime | None = None,
        subscription_id: int | None = None,
        metadata_snapshot: dict[str, Any] | None = None,
        new_subscription_params: NewSubscriptionParams | None = None,
    ) -> Payment:
        """
        Обработать успешный платёж (например, callback/webhook от провайдера).

        - находим Payment по provider_payment_id,
        - проставляем статус SUCCEEDED, paid_at, metadata_snapshot,
        - при необходимости создаём или обновляем подписку,
        - инициируем уведомление PAYMENT_SUCCEEDED.

        Идемпотентно: повторный вызов с уже обработанным provider_payment_id
        (Payment.status == SUCCEEDED) не выполняет действия повторно.
        """
        payment = await self._payments.get_by_provider_payment_id(provider_payment_id)
        if payment is None:
            raise ValueError(
                f"Payment with provider_payment_id={provider_payment_id} not found"
            )

        if payment.status == PaymentStatus.SUCCEEDED:
            logger.info(
                "payment_already_succeeded",
                payment_id=payment.id,
                provider_payment_id=provider_payment_id,
            )
            return payment

        if payment.status in (
            PaymentStatus.REFUNDED_PARTIALLY,
            PaymentStatus.REFUNDED_FULLY,
        ):
            logger.warning(
                "payment_succeeded_event_after_refund",
                payment_id=payment.id,
                provider_payment_id=provider_payment_id,
                current_status=payment.status.value,
            )
            return payment

        now = datetime.now(timezone.utc)
        payment = await self._payments.set_status(
            payment,
            status=PaymentStatus.SUCCEEDED,
            paid_at=paid_at or now,
            metadata_snapshot=metadata_snapshot,
            refundable=True,
        )

        # Если нам передали subscription_id и у платежа ещё нет привязки — привязываем.
        if subscription_id is not None and payment.subscription_id is None:
            payment = await self._payments.update(
                payment,
                subscription_id=subscription_id,
            )

        # Если subscription_id не передан и у платежа нет привязки,
        # можно создать новую подписку на основе new_subscription_params.
        if payment.subscription_id is None and new_subscription_params is not None:
            subscription = await self._subscriptions.create_for_payment(
                user_id=payment.user_id,
                tariff_id=new_subscription_params.tariff_id,
                server_id=new_subscription_params.server_id,
                marzban_username=new_subscription_params.marzban_username,
                starts_at=new_subscription_params.starts_at,
                expires_at=new_subscription_params.expires_at,
            )
            payment = await self._payments.update(
                payment,
                subscription_id=subscription.id,
            )

        # Уведомление пользователя об успешном платеже.
        if await self._notifications.notify_payment_succeeded(
            user_id=payment.user_id,
            subscription_id=payment.subscription_id,
        ):
            # После фактической отправки сообщения хендлер/сценарий должен вызвать log_success.
            pass

        return payment

    async def process_canceled_payment(
        self,
        *,
        provider_payment_id: str,
        metadata_snapshot: dict[str, Any] | None = None,
    ) -> Payment:
        """
        Обработать отменённый платеж (CANCELED) со стороны провайдера.

        Идемпотентно: повторный вызов с уже CANCELED платежом ничего не меняет.
        Если платёж уже успел стать SUCCEEDED/REFUNDED_* (нестандартный порядок
        событий от провайдера), статус не откатывается назад.
        """
        payment = await self._payments.get_by_provider_payment_id(provider_payment_id)
        if payment is None:
            raise ValueError(
                f"Payment with provider_payment_id={provider_payment_id} not found"
            )

        if payment.status == PaymentStatus.CANCELED:
            logger.info(
                "payment_already_canceled",
                payment_id=payment.id,
                provider_payment_id=provider_payment_id,
            )
            return payment

        if payment.status in (
            PaymentStatus.SUCCEEDED,
            PaymentStatus.REFUNDED_PARTIALLY,
            PaymentStatus.REFUNDED_FULLY,
        ):
            logger.warning(
                "payment_canceled_event_after_succeeded",
                payment_id=payment.id,
                provider_payment_id=provider_payment_id,
                current_status=payment.status.value,
            )
            return payment

        payment = await self._payments.set_status(
            payment,
            status=PaymentStatus.CANCELED,
            metadata_snapshot=metadata_snapshot,
            refundable=False,
        )

        # При необходимости можно отключить связанную подписку
        # через SubscriptionService.disable(..., disabled_reason=DisabledReason.PAYMENT_CANCELED),
        # когда будем дописывать сценарий.
        return payment
