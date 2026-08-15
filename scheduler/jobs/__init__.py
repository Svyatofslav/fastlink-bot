from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from database.enums import DisabledReason, NotificationType, RefundStatus
from database.models import Payment  # noqa: TC001
from database.repo import WebhookEventsRepo
from database.repo.subscriptions import SubscriptionRepo
from database.session import get_async_session_factory
from keyboards.client import main_menu_kb
from services.marzban_subscription import SubscriptionMarzbanService
from services.notifications import NotificationService
from services.payment import NewSubscriptionParams, PaymentService
from services.refund import RefundService
from services.subscription import SubscriptionService
from utils.format import format_price
from utils.i18n import t

if TYPE_CHECKING:
    from aiogram import Bot

logger = structlog.get_logger(__name__)

_REFUND_EVENT_STATUS_MAP: dict[str, RefundStatus] = {
    "refund.succeeded": RefundStatus.SUCCEEDED,
    "refund.canceled": RefundStatus.CANCELED,
    "refund.failed": RefundStatus.FAILED,
}


async def process_webhook_events(
    provider: str = "test", limit: int = 100, bot: Bot | None = None
) -> None:
    factory = get_async_session_factory()
    async with factory() as session:
        await process_webhook_events_with_session(
            session=session,
            provider=provider,
            limit=limit,
            bot=bot,
        )


async def handle_single_event(
    repo: WebhookEventsRepo, event: Any, bot: Bot | None = None
) -> None:
    """
    Разбирает одно webhook-событие и вызывает соответствующий сервис.

    Исключения намеренно не гасятся: если внутри PaymentService/RefundService
    возникла ошибка (например, Payment/Refund не найден), событие помечается
    FAILED и может быть ретраено позже. Повторные события с тем же external_id
    безопасны за счёт идемпотентности самих сервисов.
    """
    session: AsyncSession = repo.session

    payload: dict[str, Any] = event.payload if isinstance(event.payload, dict) else {}

    logger.info(
        "webhook_event_processing",
        event_id=event.id,
        provider=event.provider,
        event_type=event.event_type,
        external_id=event.external_id,
    )

    if event.provider != "yookassa":
        logger.warning(
            "webhook_event_unknown_provider",
            event_id=event.id,
            provider=event.provider,
        )
        return

    event_type = event.event_type

    if event_type == "payment.succeeded":
        await _handle_payment_succeeded(session, event, payload, bot=bot)
    elif event_type == "payment.canceled":
        await _handle_payment_canceled(session, event, payload)
    elif event_type in _REFUND_EVENT_STATUS_MAP:
        await _handle_refund_event(
            session, event, payload, _REFUND_EVENT_STATUS_MAP[event_type]
        )
    else:
        logger.warning(
            "webhook_event_unhandled_type",
            event_id=event.id,
            provider=event.provider,
            event_type=event_type,
        )


def _get_object(payload: dict[str, Any]) -> dict[str, Any]:
    obj = payload.get("object")
    if not isinstance(obj, dict):
        raise ValueError("webhook payload missing 'object'")  # noqa: TRY004 — external malformed data, not a type-usage bug
    return obj


def _get_provider_payment_id(obj: dict[str, Any]) -> str:
    provider_payment_id = obj.get("id")
    if not provider_payment_id:
        raise ValueError("payment object missing 'id'")
    return str(provider_payment_id)


def _get_metadata(obj: dict[str, Any]) -> dict[str, Any]:
    metadata = obj.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _build_metadata_snapshot(obj: dict[str, Any]) -> dict[str, Any]:
    """Собирает только нужные поля из payment-объекта, без лишнего мусора."""
    amount = obj.get("amount") or {}
    return {
        "amount_value": amount.get("value"),
        "amount_currency": amount.get("currency"),
        "paid": obj.get("paid"),
        "description": obj.get("description"),
        "metadata": _get_metadata(obj),
    }


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (ValueError, AttributeError):
        return None


def _build_new_subscription_params(
    metadata: dict[str, Any],
) -> NewSubscriptionParams | None:
    required_keys = {"tariff_id", "server_id", "marzban_username", "expires_at"}
    if not all(key in metadata for key in required_keys):
        return None
    return NewSubscriptionParams.model_validate(metadata)


async def _handle_payment_succeeded(
    session: AsyncSession, event: Any, payload: dict[str, Any], bot: Bot | None = None
) -> None:
    obj = _get_object(payload)
    provider_payment_id = _get_provider_payment_id(obj)
    metadata = _get_metadata(obj)
    metadata_snapshot = _build_metadata_snapshot(obj)
    paid_at = _parse_datetime(obj.get("created_at")) or datetime.now(UTC)

    subscription_id_raw = metadata.get("subscription_id")
    subscription_id = int(subscription_id_raw) if subscription_id_raw else None

    new_subscription_params = (
        _build_new_subscription_params(metadata) if subscription_id is None else None
    )

    logger.info(
        "webhook_payment_succeeded",
        event_id=event.id,
        provider_payment_id=provider_payment_id,
        subscription_id=subscription_id,
        amount=metadata_snapshot.get("amount_value"),
        currency=metadata_snapshot.get("amount_currency"),
    )

    payment_service = PaymentService(session)
    payment = await payment_service.process_successful_payment(
        provider_payment_id=provider_payment_id,
        paid_at=paid_at,
        subscription_id=subscription_id,
        metadata_snapshot=metadata_snapshot,
        new_subscription_params=new_subscription_params,
    )

    if payment.subscription_id is not None:
        await _ensure_subscription_activated(session, payment.subscription_id)

    if subscription_id is not None:
        tariff_id_raw = metadata.get("tariff_id")
        if tariff_id_raw is not None:
            subscription_service = SubscriptionService(session)
            await subscription_service.extend_for_payment(
                subscription_id=subscription_id,
                tariff_id=int(tariff_id_raw),
            )
            logger.info(
                "subscription_extended_after_payment",
                subscription_id=subscription_id,
                payment_id=payment.id,
            )
        else:
            logger.warning(
                "subscription_extension_missing_tariff_id",
                subscription_id=subscription_id,
                payment_id=payment.id,
            )

    is_donation = (
        payment.metadata_snapshot is not None
        and payment.metadata_snapshot.get("metadata", {}).get("type") == "donation"
    )
    if is_donation:
        await notify_donation_succeeded(bot, session, payment)
    else:
        await _notify_payment_succeeded(bot, session, payment)


async def _notify_payment_succeeded(
    bot: Bot | None, session: AsyncSession, payment: Payment
) -> None:
    """
    Отправляет push пользователю после успешной оплаты/активации подписки,
    а затем главное меню для быстрого перехода к "Мои подписки".

    Дедупликация через NotificationLog (should_send): повторный вызов на том
    же payment (retry webhook-события) не отправит сообщение дважды.
    Ошибка Telegram API (бан бота, deleted account) при отправке основного
    текста логируется как FAILED и не должна ронять обработку
    webhook-события. Падение отправки меню (второе сообщение) не считается
    провалом всего уведомления — пользователь уже получил главный текст,
    поэтому такая ошибка только логируется как warning, без записи FAILED
    (иначе при повторной обработке того же события пользователю повторно
    ушёл бы уже доставленный текст об оплате).
    """
    if bot is None:
        logger.warning("payment_succeeded_notify_skipped_no_bot", payment_id=payment.id)
        return

    notifications = NotificationService(session)
    should_send = await notifications.should_send(
        user_id=payment.user_id,
        notification_type=NotificationType.PAYMENT_SUCCEEDED,
        subscription_id=payment.subscription_id,
    )
    if not should_send:
        return

    user = payment.user
    if user is None:
        logger.warning("payment_succeeded_notify_no_user", payment_id=payment.id)
        return

    lang = user.language_code or "ru"
    price = format_price(payment.amount, payment.currency)
    text = t("payment.succeeded.message", lang, price=price)

    try:
        await bot.send_message(chat_id=user.telegram_id, text=text)
    except Exception as exc:
        logger.exception(
            "payment_succeeded_notify_failed",
            payment_id=payment.id,
            user_id=payment.user_id,
            exc_info=exc,
        )
        await notifications.log_failure(
            user_id=payment.user_id,
            notification_type=NotificationType.PAYMENT_SUCCEEDED,
            subscription_id=payment.subscription_id,
            payload={"payment_id": payment.id},
        )
        return

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=t("main.menu.title", lang),
            reply_markup=main_menu_kb(user),
        )
    except Exception:  # noqa: BLE001 — фоновая job не должна падать из-за сбоя доставки уведомления
        logger.warning(
            "payment_succeeded_menu_send_failed",
            payment_id=payment.id,
            user_id=payment.user_id,
        )

    await notifications.log_success(
        user_id=payment.user_id,
        notification_type=NotificationType.PAYMENT_SUCCEEDED,
        subscription_id=payment.subscription_id,
        payload={"payment_id": payment.id},
    )


async def notify_donation_succeeded(
    bot: Bot | None, session: AsyncSession, payment: Payment
) -> None:
    """Отправляет пользователю уведомление об успешном донате.
    Дедуплицируется через NotificationLog по NotificationType.DONATION_SUCCEEDED,
    защищая от повторной отправки при retry обработки webhook-события."""
    if bot is None:
        logger.warning(
            "donation_succeeded_notify_skipped_no_bot", payment_id=payment.id
        )
        return

    notifications = NotificationService(session)
    should_send = await notifications.should_send(
        user_id=payment.user_id,
        notification_type=NotificationType.DONATION_SUCCEEDED,
    )
    if not should_send:
        return

    user = payment.user
    if user is None:
        logger.warning("donation_succeeded_notify_no_user", payment_id=payment.id)
        return

    lang = user.language_code or "ru"
    price = format_price(payment.amount, payment.currency)
    text = t("donation.succeeded.message", lang, price=price)

    try:
        await bot.send_message(chat_id=user.telegram_id, text=text)
    except Exception as exc:
        logger.exception(
            "donation_succeeded_notify_failed",
            payment_id=payment.id,
            user_id=payment.user_id,
            exc_info=exc,
        )
        await notifications.log_failure(
            user_id=payment.user_id,
            notification_type=NotificationType.DONATION_SUCCEEDED,
            payload={"payment_id": payment.id},
        )
        return

    await notifications.log_success(
        user_id=payment.user_id,
        notification_type=NotificationType.DONATION_SUCCEEDED,
        payload={"payment_id": payment.id},
    )


async def _ensure_subscription_activated(
    session: AsyncSession, subscription_id: int
) -> None:
    """
    Активировать подписку в Marzban, если это ещё не было сделано.

    Идемпотентно: если subscription_url уже выставлен, значит create_user
    в Marzban уже прошёл успешно ранее — повторный вызов не выполняется.
    Это защищает от дублирования пользователей в Marzban при retry
    webhook-событий (например, если предыдущая попытка активации упала
    из-за временной недоступности Marzban API).
    """
    subscriptions = SubscriptionRepo(session)
    subscription = await subscriptions.get_by_id(subscription_id)
    if subscription is None:
        logger.warning(
            "subscription_not_found_for_activation",
            subscription_id=subscription_id,
        )
        return

    if subscription.subscription_url is not None:
        logger.debug(
            "subscription_already_activated",
            subscription_id=subscription_id,
        )
        return

    marzban_service = SubscriptionMarzbanService(session)
    await marzban_service.activate_subscription(subscription_id)
    logger.info(
        "subscription_activated_in_marzban",
        subscription_id=subscription_id,
    )


async def _handle_payment_canceled(
    session: AsyncSession, event: Any, payload: dict[str, Any]
) -> None:
    obj = _get_object(payload)
    provider_payment_id = _get_provider_payment_id(obj)
    metadata_snapshot = _build_metadata_snapshot(obj)

    logger.info(
        "webhook_payment_canceled",
        event_id=event.id,
        provider_payment_id=provider_payment_id,
    )

    payment_service = PaymentService(session)
    await payment_service.process_canceled_payment(
        provider_payment_id=provider_payment_id,
        metadata_snapshot=metadata_snapshot,
    )


async def _handle_refund_event(
    session: AsyncSession,
    event: Any,
    payload: dict[str, Any],
    status: RefundStatus,
) -> None:
    obj = _get_object(payload)
    provider_refund_id = obj.get("id")
    if not provider_refund_id:
        raise ValueError("refund object missing 'id'")

    logger.info(
        "webhook_refund_event",
        event_id=event.id,
        provider_refund_id=provider_refund_id,
        status=status.value,
    )

    refund_service = RefundService(session)
    await refund_service.process_refund_result(
        provider_refund_id=str(provider_refund_id),
        status=status,
        raw_payload=obj,
    )


async def expire_overdue_subscriptions() -> None:
    factory = get_async_session_factory()
    async with factory() as session:
        repo = SubscriptionRepo(session)
        service = SubscriptionService(session)
        try:
            expired = await repo.get_expired()
            if not expired:
                return
            logger.info("subscriptions_expire_started", count=len(expired))
            for subscription in expired:
                try:
                    await service.disable(
                        subscription_id=subscription.id,
                        disabled_reason=DisabledReason.EXPIRED,
                        admin_id=None,
                    )
                except Exception as exc:
                    logger.exception(
                        "subscription_expire_failed",
                        subscription_id=subscription.id,
                        exc_info=exc,
                    )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("subscriptions_expire_batch_failed")


async def _send_expiration_reminders(within_days: int) -> None:
    factory = get_async_session_factory()
    notify_method_name = (
        "notify_sub_expires_3d" if within_days == 3 else "notify_sub_expires_1d"
    )
    async with factory() as session:
        repo = SubscriptionRepo(session)
        notifications = NotificationService(session)
        try:
            expiring = await repo.get_expiring(within_days=within_days)
            if not expiring:
                return
            logger.info(
                "subscriptions_reminder_started",
                within_days=within_days,
                count=len(expiring),
            )
            notify = getattr(notifications, notify_method_name)
            for subscription in expiring:
                try:
                    should_notify = await notify(
                        user_id=subscription.user_id,
                        subscription_id=subscription.id,
                    )
                    if should_notify:
                        # TODO: фактическая отправка сообщения пользователю
                        # (bot.send_message) + notifications.log_success/log_failure
                        # добавится, когда будет готов слой доставки уведомлений.
                        pass
                except Exception as exc:
                    logger.exception(
                        "subscription_reminder_failed",
                        subscription_id=subscription.id,
                        within_days=within_days,
                        exc_info=exc,
                    )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "subscriptions_reminder_batch_failed", within_days=within_days
            )


async def send_expiration_reminders_3d() -> None:
    await _send_expiration_reminders(within_days=3)


async def send_expiration_reminders_1d() -> None:
    await _send_expiration_reminders(within_days=1)


async def process_webhook_events_with_session(
    session: AsyncSession,
    provider: str = "test",
    limit: int = 100,
    bot: Bot | None = None,
) -> None:
    repo = WebhookEventsRepo(session=session)
    try:
        events = await repo.list_pending(provider=provider, limit=limit)
        if not events:
            return

        logger.info(
            "webhook_events_processing_started",
            provider=provider,
            count=len(events),
        )

        for event in events:
            try:
                await handle_single_event(repo, event, bot=bot)
                await repo.mark_done(event.id)
            except Exception as exc:
                logger.exception(
                    "webhook_event_processing_failed",
                    event_id=event.id,
                    provider=event.provider,
                    exc_info=exc,
                )
                await repo.mark_failed(event.id, str(exc))

            await session.commit()  # <-- ДОБАВЛЕНО: коммитим после каждого события,
            # а не одним пакетом в конце. Иначе FOR UPDATE
            # SKIP LOCKED из list_pending() не даст эффекта —
            # блокировки на строках снимутся только после
            # commit, и до этого момента второй воркер тоже
            # будет их "пропускать" впустую, а не начинать
            # обрабатывать следующие события сразу.

    except Exception:
        await session.rollback()
        logger.exception("webhook_events_batch_failed")
