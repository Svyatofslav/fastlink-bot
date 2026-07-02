from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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
        """
        refund_request = await self._refund_requests.get_by_id(refund_request_id)
        if refund_request is None:
            raise ValueError(f"RefundRequest {refund_request_id} not found")

        payment = refund_request.payment

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
        """
        refund = await self._refunds.get_by_provider_refund_id(provider_refund_id)
        if refund is None:
            raise ValueError(
                f"Refund with provider_refund_id={provider_refund_id} not found"
            )

        now = datetime.now(timezone.utc)

        refund = await self._refunds.set_status(
            refund,
            status=status,
            raw_payload=raw_payload,
            completed_at=now,
        )

        payment = refund.payment

        # Обновляем refunded_amount и статус платежа.
        new_refunded_amount = payment.refunded_amount + refund.amount

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
