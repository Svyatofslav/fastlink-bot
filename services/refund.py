from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from database.enums import (
    AdminActionType,
    AdminEntityType,
    DisabledReason,
    PaymentStatus,
    RefundRequestStatus,
    RefundStatus,
)
from database.models import Refund, RefundRequest  # noqa: TC001
from database.repo.payments import PaymentRepo
from database.repo.refund_requests import RefundRequestRepo
from database.repo.refunds import RefundRepo
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


def _next_payment_status(
    *, new_refunded_amount: int, payment_amount: int
) -> PaymentStatus:
    if new_refunded_amount < payment_amount:
        return PaymentStatus.REFUNDED_PARTIALLY
    return PaymentStatus.REFUNDED_FULLY


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
        return await self._refund_requests.create(
            user_id=user_id,
            payment_id=payment_id,
            subscription_id=subscription_id,
            reason=reason,
            status=RefundRequestStatus.NEW,
            admin_comment=None,
            reviewed_by_admin_id=None,
            reviewed_at=None,
        )

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

        now = datetime.now(UTC) if admin_id is not None else None

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

    async def _resolve_refund_after_race(
        self, *, refund_request_id: int, provider_refund_id: str | None
    ) -> Refund | None:
        """Пытается найти уже созданный Refund после IntegrityError-гонки."""
        existing_refund: Refund | None = None
        if provider_refund_id is not None:
            existing_refund = await self._refunds.get_by_provider_refund_id(
                provider_refund_id
            )
        if existing_refund is None:
            fallback_refunds = await self._refunds.get_by_refund_request(
                refund_request_id
            )
            existing_refund = fallback_refunds[0] if fallback_refunds else None
        return existing_refund

    async def _find_active_existing_refund(
        self, refund_request_id: int
    ) -> Refund | None:
        existing_refunds = await self._refunds.get_by_refund_request(refund_request_id)
        active_existing = [
            r for r in existing_refunds if r.status != RefundStatus.CANCELED
        ]
        return active_existing[0] if active_existing else None

    async def _validate_refund_amount(
        self, *, payment: Any, refund_request_id: int, amount: int
    ) -> None:
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

        existing = await self._find_active_existing_refund(refund_request_id)
        if existing is not None:
            logger.info(
                "refund_idempotency_hit_before_insert",
                refund_id=existing.id,
                refund_request_id=refund_request_id,
            )
            return existing

        payment = refund_request.payment
        await self._validate_refund_amount(
            payment=payment, refund_request_id=refund_request_id, amount=amount
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
            existing_refund = await self._resolve_refund_after_race(
                refund_request_id=refund_request_id,
                provider_refund_id=provider_refund_id,
            )
            if existing_refund is None:
                raise
            return existing_refund

        await self._session.flush()
        return refund

    def _check_idempotent_or_stale(
        self, refund: Refund, status: RefundStatus, provider_refund_id: str
    ) -> bool:
        """True — событие нужно проигнорировать (уже обработано или устарело)."""
        if refund.status == status and refund.completed_at is not None:
            logger.info(
                "refund_event_already_processed",
                refund_id=refund.id,
                provider_refund_id=provider_refund_id,
                status=status.value,
            )
            return True

        if (
            refund.status
            in (RefundStatus.SUCCEEDED, RefundStatus.FAILED, RefundStatus.CANCELED)
            and refund.status != status
        ):
            logger.warning(
                "refund_status_transition_after_terminal_state",
                refund_id=refund.id,
                provider_refund_id=provider_refund_id,
                current_status=refund.status.value,
                incoming_status=status.value,
            )
            return True

        return False

    async def _apply_successful_refund_side_effects(self, payment: Any) -> None:
        if payment.subscription_id is not None:
            await self._subscriptions.disable(
                subscription_id=payment.subscription_id,
                disabled_reason=DisabledReason.REFUNDED,
                admin_id=None,
            )
        await self._notifications.notify_refund_processed(
            user_id=payment.user_id,
            subscription_id=payment.subscription_id,
        )

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

        if self._check_idempotent_or_stale(refund, status, provider_refund_id):
            return refund

        now = datetime.now(UTC)
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
            return await self._refunds.set_status(
                refund,
                status=RefundStatus.FAILED,
                raw_payload=raw_payload,
                completed_at=now,
            )

        refund = await self._refunds.set_status(
            refund,
            status=status,
            raw_payload=raw_payload,
            completed_at=now,
        )

        payment_status = payment.status
        if status == RefundStatus.SUCCEEDED:
            payment_status = _next_payment_status(
                new_refunded_amount=new_refunded_amount,
                payment_amount=payment.amount,
            )

        payment = await self._payments.set_status(
            payment,
            status=payment_status,
            refunded_amount=new_refunded_amount,
        )

        if status == RefundStatus.SUCCEEDED:
            await self._apply_successful_refund_side_effects(payment)

        return refund
