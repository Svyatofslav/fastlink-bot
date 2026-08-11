from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from clients.yookassa import FakeYooKassaClient, YooKassaClient, YooKassaClientError
from config import get_settings
from database.enums import PaymentProvider, PaymentStatus
from database.models import Payment  # noqa: TC001
from database.repo.payments import PaymentRepo
from domain.donation_metadata import build_yookassa_donation_flat_metadata
from domain.purchase_metadata import build_yookassa_flat_metadata
from schemas.dto import NewSubscriptionParams  # noqa: TC001
from services.notifications import NotificationService
from services.subscription import SubscriptionService

logger = structlog.get_logger(__name__)


def get_yookassa_client() -> YooKassaClient:
    """
    Фабрика клиента YooKassa.

    Пока нет реальных ключей или интеграция выключена (флаг в settings),
    возвращает FakeYooKassaClient, который не делает HTTP-запросов и
    отдаёт предсказуемую confirmation_url.

    Когда подключим боевую YooKassa, будет достаточно выставить флаг
    в settings, чтобы вернулся реальный клиент.
    """
    settings = get_settings()
    # Если у тебя ещё нет поля yookassa_enabled в Settings, можно временно
    # считать его всегда False или завести с дефолтом False.
    if not getattr(settings, "yookassa_enabled", False):
        return FakeYooKassaClient()
    return YooKassaClient()


class PaymentService:
    """
    Application-уровневый сервис для работы с платежами.

    Оркестрирует:
    - создание записи Payment перед обращением к провайдеру,
    - обработку событий от провайдера (успех/отмена),
    - привязку Payment к Subscription,
    - уведомления пользователя об успешном платеже.
    """

    def __init__(
        self, session: AsyncSession, yookassa_client: YooKassaClient | None = None
    ) -> None:
        self._session = session
        self._payments = PaymentRepo(session)
        self._notifications = NotificationService(session)
        self._subscriptions = SubscriptionService(session)
        self._yookassa = yookassa_client or get_yookassa_client()

    async def create_payment(
        self,
        *,
        user_id: int,
        amount: int,
        currency: str,
        provider: PaymentProvider = PaymentProvider.YOOKASSA,
        subscription_id: int | None = None,
        idempotency_key: str,
        metadata_snapshot: dict[str, Any] | None = None,
    ) -> Payment:
        """
        Создаёт Payment и платёжную ссылку у провайдера.

        Идемпотентно по idempotency_key: сначала пытаемся найти уже
        существующий Payment (обычный повторный клик), а если гонка
        всё же произошла между SELECT и INSERT — ловим IntegrityError
        от уникального constraint payments.idempotence_key и отдаём
        найденную по ключу запись вместо падения наружу. Паттерн
        аналогичен WebhookEventsRepo.create_event для external_id.
        """
        existing = await self._payments.get_by_idempotence_key(idempotency_key)
        if existing is not None:
            logger.info(
                "payment_idempotency_hit_before_insert",
                payment_id=existing.id,
                idempotency_key=idempotency_key,
            )
            return existing

        try:
            async with self._session.begin_nested():
                payment = await self._payments.create(
                    user_id=user_id,
                    subscription_id=subscription_id,
                    provider=provider,
                    provider_payment_id=None,
                    amount=amount,
                    currency=currency,
                    status=PaymentStatus.PENDING,
                    idempotence_key=idempotency_key,
                    metadata_snapshot=metadata_snapshot,
                    paid_at=None,
                    refundable=False,
                    refunded_amount=0,
                )
        except IntegrityError:
            logger.info(
                "payment_idempotency_race_detected",
                idempotency_key=idempotency_key,
            )
            existing = await self._payments.get_by_idempotence_key(idempotency_key)
            if existing is None:
                raise
            return existing

        await self._session.flush()

        flat_metadata: dict[str, str] = {}
        if metadata_snapshot is not None:
            if metadata_snapshot.get("type") == "donation":
                flat_metadata = build_yookassa_donation_flat_metadata(metadata_snapshot)
            else:
                flat_metadata = build_yookassa_flat_metadata(metadata_snapshot)

        try:
            link = await self._yookassa.create_payment_link(
                amount=amount,
                currency=currency,
                description=f"FastLink payment #{payment.id}",
                idempotency_key=idempotency_key,
                return_url=self._build_return_url(payment.id),
                metadata=flat_metadata,
            )
        except YooKassaClientError:
            logger.exception(
                "yookassa_create_payment_link_failed", payment_id=payment.id
            )
            raise

        updated_payment = await self._payments.update(
            payment,
            provider_payment_id=link.provider_payment_id,
            confirmation_url=link.confirmation_url,
        )

        if updated_payment.confirmation_url is None:
            # Не должно происходить: YooKassaPaymentLink.confirmation_url — обязательное
            # строковое поле (clients/yookassa.py), FakeYooKassaClient всегда отдаёт
            # заглушку. Проверка — защита от будущих изменений контракта клиента,
            # а не ожидаемый бизнес-сценарий.
            raise RuntimeError(
                f"Payment {updated_payment.id} создан без confirmation_url — "
                "нарушен контракт платёжного клиента"
            )

        return updated_payment

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

        return await self._payments.update(
            payment,
            provider_payment_id=provider_payment_id,
        )

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

        now = datetime.now(UTC)
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

        # При необходимости можно отключить связанную подписку
        # через SubscriptionService.disable(..., disabled_reason=DisabledReason.PAYMENT_CANCELED),
        # когда будем дописывать сценарий.
        return await self._payments.set_status(
            payment,
            status=PaymentStatus.CANCELED,
            metadata_snapshot=metadata_snapshot,
            refundable=False,
        )

    async def cancel_pending_payment(self, *, payment_id: int) -> Payment:
        """
        Отменить платёж по инициативе пользователя, пока он ещё PENDING.

        Используется до подключения провайдера (clients/yookassa.py) —
        process_canceled_payment здесь неприменим, так как ищет платёж
        по provider_payment_id, которого ещё нет (интеграция не вызывалась).
        Идемпотентно: если платёж уже не PENDING, просто возвращаем его как есть.
        """
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != PaymentStatus.PENDING:
            return payment

        return await self._payments.set_status(
            payment,
            status=PaymentStatus.CANCELED,
            refundable=False,
        )

    @staticmethod
    def _build_return_url(payment_id: int) -> str:
        """
        Собирает URL, на который YooKassa вернёт пользователя после оплаты.

        Сейчас это может быть deeplink бота, например:
        https://t.me/<bot>?start=payment_<id>
        Конкретный формат можно уточнить позже и вынести в settings.
        """
        settings = get_settings()
        # Если в settings ещё нет bot_deep_link_base, можно временно захардкодить
        # или добавить с дефолтом.
        base = getattr(settings, "bot_deep_link_base", "")
        if base:
            return f"{base}?start=payment_{payment_id}"
        # Временно возвращаем заглушку; в бою лучше всегда иметь валидный URL.
        return "https://example.com/payment_return"
