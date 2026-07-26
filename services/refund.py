from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from database.enums import (
    RefundRequestStatus,
    RefundStatus,
    PaymentStatus,
    DisabledReason,
    AdminActionType,
    AdminEntityType,
)
from database.models import RefundRequest, Refund
from database.repo.refund_requests import RefundRequestRepo
from database.repo.refunds import RefundRepo
from database.repo.payments import PaymentRepo
from services.admin_actions import AdminActionLogService
from services.notifications import NotificationService
from services.subscription import SubscriptionService

logger = structlog.get_logger(__name__)


class RefundAmountExceedsPaymentError(ValueError):
    """Сумма рефанда превышает неоплаченный остаток платежа."""

    def __init__(self, payment_id: int, requested: int, available: int) -> None:
        self.payment_id = payment_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Refund amount {requested} exceeds available {available} "
            f"for payment {payment_id}"
        )


class RefundService:
    """
    Application-уровневый сервис для работы с возвратами.

    Оркестрирует:
    - создание и модерацию RefundRequest,
    - создание Refund и обновление статусов Payment/Subscription,
    - уведомления пользователя и аудит действий админа.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._refund_requests = RefundRequestRepo(session)
        self._refunds = RefundRepo(session)
        self._payments = PaymentRepo(session)

        self._notifications = NotificationService(session)
        self._subscriptions = SubscriptionService(session)
        self._admin_actions = AdminActionLogService(session)

    async def create_refund_request(
        self,
        *,
        user_id: int,
        payment_id: int,
        subscription_id: int | None,
        reason: str,
    ) -> RefundRequest:
        """
        Создать новую заявку на возврат от пользователя (RefundRequestStatus.NEW).
        """
        refund_request = await self._refund_requests.create(
            user_id=user_id,
            payment_id=payment_id,
            subscription_id=subscription_id,
            reason=reason,
            status=RefundRequestStatus.NEW,
            admin_comment=None,
            reviewed_by_admin_id=None,
            reviewed_at=None,
        )
        return refund_request

    async def set_request_status(
        self,
        *,
        refund_request_id: int,
        status: RefundRequestStatus,
        admin_id: int | None = None,
        admin_comment: str | None = None,
    ) -> RefundRequest:
        """
        Изменить статус заявки на возврат (IN_REVIEW/APPROVED/REJECTED/FAILED/PROCESSED).
        При наличии admin_id пишет аудит.
        """
        refund_request = await self._refund_requests.get_by_id(refund_request_id)
        if refund_request is None:
            raise ValueError(f"RefundRequest {refund_request_id} not found")

        now = datetime.now(timezone.utc) if admin_id is not None else None

        refund_request = await self._refund_requests.set_status(
            refund_request,
            status=status,
            admin_comment=admin_comment,
            reviewed_by_admin_id=admin_id,
            reviewed_at=now,
        )

        if admin_id is not None:
            action = None
            if status == RefundRequestStatus.APPROVED:
                action = AdminActionType.APPROVE_REFUND
            elif status == RefundRequestStatus.REJECTED:
                action = AdminActionType.REJECT_REFUND
            elif status in (RefundRequestStatus.PROCESSED, RefundRequestStatus.FAILED):
                action = AdminActionType.PROCESS_REFUND

            if action is not None:
                await self._admin_actions.log_action(
                    admin_id=admin_id,
                    action=action,
                    entity_type=AdminEntityType.REFUND_REQUEST,
                    entity_id=refund_request.id,
                    payload_before=None,
                    payload_after={
                        "status": refund_request.status.value,
                        "admin_comment": refund_request.admin_comment,
                    },
                    comment=admin_comment,
                )

        return refund_request

    async def create_refund_for_request(
        self,
        *,
        refund_request_id: int,
        amount: int,
        currency: str,
        provider_refund_id: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> Refund:
        """
        Создать запись Refund (status=PENDING) по утверждённой заявке.

        Идемпотентно по refund_request_id: если для этой заявки уже есть
        незавершённый Refund (например, два админа одновременно нажали
        "одобрить"), возвращаем существующую запись вместо создания
        дубликата. Дополнительно ловим IntegrityError по
        uq_refunds_provider_refund_id на случай гонки с уже известным
        provider_refund_id.

        Валидирует, что сумма рефанда не превышает неоплаченный остаток
        payment.amount с учётом уже существующих активных (PENDING/SUCCEEDED)
        рефандов по этому же платежу — защита от одобрения второго частичного
        рефанда, который в сумме с первым превысит стоимость покупки.
        """
        refund_request = await self._refund_requests.get_by_id(refund_request_id)
        if refund_request is None:
            raise ValueError(f"RefundRequest {refund_request_id} not found")

        existing_refunds = await self._refunds.get_by_refund_request(refund_request_id)
        active_existing = [
            r for r in existing_refunds if r.status != RefundStatus.CANCELED
        ]
        if active_existing:
            existing = active_existing[0]
            logger.info(
                "refund_idempotency_hit_before_insert",
                refund_id=existing.id,
                refund_request_id=refund_request_id,
            )
            return existing

        payment = refund_request.payment

        if amount <= 0:
            raise ValueError(f"Refund amount must be positive, got {amount}")

        active_amount_for_payment = sum(
            r.amount
            for r in await self._refunds.get_by_payment(payment.id)
            if r.status in (RefundStatus.PENDING, RefundStatus.SUCCEEDED)
        )
        available = payment.amount - active_amount_for_payment
        if amount > available:
            logger.warning(
                "refund_amount_exceeds_available",
                payment_id=payment.id,
                refund_request_id=refund_request_id,
                requested=amount,
                available=available,
            )
            raise RefundAmountExceedsPaymentError(
                payment_id=payment.id, requested=amount, available=available
            )

        try:
            async with self._session.begin_nested():
                refund = await self._refunds.create(
                    payment_id=payment.id,
                    refund_request_id=refund_request.id,
                    provider=payment.provider,
                    provider_refund_id=provider_refund_id,
                    amount=amount,
                    currency=currency,
                    status=RefundStatus.PENDING,
                    raw_payload=raw_payload,
                    completed_at=None,
                )
        except IntegrityError:
            logger.info(
                "refund_idempotency_race_detected",
                refund_request_id=refund_request_id,
                provider_refund_id=provider_refund_id,
            )
            existing = None
            if provider_refund_id is not None:
                existing = await self._refunds.get_by_provider_refund_id(
                    provider_refund_id
                )
            if existing is None:
                fallback_refunds = await self._refunds.get_by_refund_request(
                    refund_request_id
                )
                existing = fallback_refunds[0] if fallback_refunds else None
            if existing is None:
                raise
            return existing

        await self._session.flush()
        return refund

    async def process_refund_result(
        self,
        *,
        provider_refund_id: str,
        status: RefundStatus,
        raw_payload: dict[str, Any] | None = None,
    ) -> Refund:
        """
        Обработать результат рефанда (например, webhook от платёжного провайдера).

        - находим Refund по provider_refund_id,
        - выставляем статус и completed_at,
        - обновляем Payment.refunded_amount и Payment.status,
        - при успехе отключаем подписку (DisabledReason.REFUNDED),
        - отправляем пользователю уведомление REFUND_PROCESSED.

        Идемпотентно: повторное событие с тем же status для уже завершённого
        Refund не меняет состояние повторно и не задваивает суммы.

        Защитная проверка: если из-за гонки/аномального payload сумма после
        применения этого рефанда превысила бы payment.amount, рефанд
        помечается FAILED без изменения Payment — это не должно приводить
        к retry вебхука (сумма от провайдера не изменится), поэтому исключение
        не пробрасывается наружу.
        """
        refund = await self._refunds.get_by_provider_refund_id(provider_refund_id)
        if refund is None:
            raise ValueError(
                f"Refund with provider_refund_id={provider_refund_id} not found"
            )

        if refund.status == status and refund.completed_at is not None:
            logger.info(
                "refund_event_already_processed",
                refund_id=refund.id,
                provider_refund_id=provider_refund_id,
                status=status.value,
            )
            return refund

        if (
            refund.status
            in (
                RefundStatus.SUCCEEDED,
                RefundStatus.FAILED,
                RefundStatus.CANCELED,
            )
            and refund.status != status
        ):
            logger.warning(
                "refund_status_transition_after_terminal_state",
                refund_id=refund.id,
                provider_refund_id=provider_refund_id,
                current_status=refund.status.value,
                incoming_status=status.value,
            )
            return refund

        now = datetime.now(timezone.utc)

        payment = refund.payment
        new_refunded_amount = payment.refunded_amount + refund.amount

        if status == RefundStatus.SUCCEEDED and new_refunded_amount > payment.amount:
            logger.error(
                "refund_amount_exceeds_payment_defensive_check",
                refund_id=refund.id,
                payment_id=payment.id,
                payment_amount=payment.amount,
                already_refunded=payment.refunded_amount,
                incoming_refund_amount=refund.amount,
            )
            refund = await self._refunds.set_status(
                refund,
                status=RefundStatus.FAILED,
                raw_payload=raw_payload,
                completed_at=now,
            )
            return refund

        refund = await self._refunds.set_status(
            refund,
            status=status,
            raw_payload=raw_payload,
            completed_at=now,
        )

        payment_status = payment.status
        if status == RefundStatus.SUCCEEDED:
            if new_refunded_amount < payment.amount:
                payment_status = PaymentStatus.REFUNDED_PARTIALLY
            else:
                payment_status = PaymentStatus.REFUNDED_FULLY

        payment = await self._payments.set_status(
            payment,
            status=payment_status,
            refunded_amount=new_refunded_amount,
        )

        # При успешном рефанде можно отключить подписку.
        if status == RefundStatus.SUCCEEDED and payment.subscription_id is not None:
            await self._subscriptions.disable(
                subscription_id=payment.subscription_id,
                disabled_reason=DisabledReason.REFUNDED,
                admin_id=None,
            )

        # Уведомление пользователя о завершённой обработке рефанда.
        if await self._notifications.notify_refund_processed(
            user_id=payment.user_id,
            subscription_id=payment.subscription_id,
        ):
            # После фактической отправки сообщения хендлер/сценарий должен вызвать log_success.
            pass

        return refund
