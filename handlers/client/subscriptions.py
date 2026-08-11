from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING, cast

import qrcode
from aiogram import Router
from aiogram.types import BufferedInputFile

from clients.marzban import MarzbanClient, MarzbanClientError
from database.enums import PaymentProvider, SubscriptionStatus
from database.repo.servers import ServerRepo
from database.repo.subscriptions import SubscriptionRepo
from database.repo.tariffs import TariffRepo
from domain.purchase_metadata import build_purchase_metadata
from domain.subscription_extension import compute_extension
from handlers.client.callback_utils import extract_callback_id as _extract_callback_id
from handlers.client.menu import render_main_menu
from keyboards.client import (
    CB_MENU_MY_SUBS,
    CB_SUB_CONFIG_LINK,
    CB_SUB_CONFIG_QR,
    CB_SUB_EXTEND,
    CB_SUB_HELP,
    CB_SUB_LINK,
    CB_SUB_PREFIX,
    CB_SUB_QR,
    back_to_main_kb,
    my_subs_list_kb,
    payment_kb,
    subscription_card_kb,
    tariffs_kb,
)
from services.payment import PaymentService
from states.purchase import (
    DATA_EXTEND_SUBSCRIPTION_ID,
    DATA_IS_EXTEND,
    DATA_SERVER_ID,
    PurchaseStates,
    build_purchase_data,
    clear_purchase_state,
)
from utils.format import format_data_limit, format_date, format_price, format_traffic
from utils.i18n import t

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext
    from aiogram.types import CallbackQuery, Message
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models import Server, Subscription, Tariff, User


router = Router(name="client-subscriptions")


def _get_callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    if message is None or not hasattr(message, "edit_text"):
        return None
    return cast("Message", message)


def _build_subscription_card_context(
    subscription: Subscription,
    server: Server | None,
    tariff: Tariff | None,
    lang: str,
) -> dict[str, str]:
    server_name = server.name if server else t("subs.server_fallback", lang)
    tariff_name = tariff.name if tariff else t("subs.tariff_fallback", lang)

    status_value = getattr(subscription.status, "value", subscription.status)
    status_label = (
        t("subs.status_active", lang)
        if status_value == SubscriptionStatus.ACTIVE.value
        else t("subs.status_disabled", lang)
    )

    period_text = t(
        "subs.period_line",
        lang,
        starts_at=format_date(subscription.starts_at),
        expires_at=format_date(subscription.expires_at),
    )

    price_text = ""
    if tariff is not None:
        price_text = t(
            "subs.price_line",
            lang,
            price=format_price(tariff.price_amount, tariff.price_currency),
        )

    traffic_text = ""
    data_limit = subscription.data_limit_bytes
    if data_limit and data_limit > 0:
        traffic_text = t(
            "subs.traffic_line",
            lang,
            traffic=format_traffic(subscription.data_used_bytes, data_limit),
        )

    return {
        "server_name": server_name,
        "tariff_name": tariff_name,
        "status_label": status_label,
        "period_line": period_text,
        "price_line": price_text,
        "traffic_line": traffic_text,
    }


def _make_qr_bytes(data: str) -> bytes:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


async def _get_owned_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    prefix: str,
) -> Subscription | None:
    """Достаёт подписку по callback_data и проверяет, что она принадлежит пользователю."""
    lang = user.language_code or "ru"
    sub_id = _extract_callback_id(callback.data, prefix)
    if sub_id is None:
        await callback.answer(t("subs.invalid_id", lang), show_alert=True)
        return None

    subscription = await SubscriptionRepo(session).get_by_id(sub_id)
    if subscription is None or subscription.user_id != user.id:
        await callback.answer(t("subs.not_found", lang), show_alert=True)
        return None

    return subscription


async def _get_marzban_config_link(
    subscription: Subscription,
    lang: str,
    callback: CallbackQuery,
) -> str | None:
    """Забирает актуальную config-ссылку из Marzban для подписки."""
    marzban = MarzbanClient()
    try:
        user_info = await marzban.get_user(subscription.marzban_username)
    except MarzbanClientError:
        await callback.answer(t("subs.config_link_failed", lang), show_alert=True)
        return None
    finally:
        await marzban.aclose()

    config_link = marzban.get_primary_config_link(user_info)
    if config_link is None:
        await callback.answer(t("subs.config_link_unavailable", lang), show_alert=True)
        return None

    return config_link


async def _prepare_subscription_action(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    prefix: str,
) -> tuple[Message, Subscription] | None:
    """Общая подготовка: проверка сообщения + владение подпиской.
    Используется в on_subscription_link/qr/config_link/config_qr."""
    message = _get_callback_message(callback)
    if message is None:
        await callback.answer()
        return None

    subscription = await _get_owned_subscription(callback, session, user, prefix)
    if subscription is None:
        return None

    return message, subscription


@router.callback_query(lambda c: c.data == CB_MENU_MY_SUBS)
async def on_my_subscriptions(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """
    Обработчик кнопки "📱 Мои подписки" в главном меню.
    Показывает список подписок пользователя или сообщение, что их нет.
    """
    message = _get_callback_message(callback)
    if message is None:
        await callback.answer()
        return

    await state.clear()

    lang = user.language_code or "ru"
    subs_repo = SubscriptionRepo(session)
    servers_repo = ServerRepo(session)

    subscriptions = await subs_repo.get_all_by_user(user.id)

    if not subscriptions:
        text = t("subs.none_yet", lang)
        await message.edit_text(text, reply_markup=back_to_main_kb(user))
        await callback.answer()
        return

    server_ids = {sub.server_id for sub in subscriptions if sub.server_id is not None}
    servers_by_id: dict[int, Server] = {}
    if server_ids:
        servers = await servers_repo.get_active()
        servers_by_id = {s.id: s for s in servers if s.id in server_ids}

    text = t("subs.list_title", lang)
    await message.edit_text(
        text,
        reply_markup=my_subs_list_kb(subscriptions, servers_by_id, user),
    )
    await callback.answer()


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_SUB_PREFIX}:")
)
async def on_subscription_card(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """
    Открыть карточку конкретной подписки: детали, способы подключения, продление, инструкция.
    """
    message = _get_callback_message(callback)
    if message is None:
        await callback.answer()
        return

    await state.clear()

    lang = user.language_code or "ru"
    subs_repo = SubscriptionRepo(session)
    servers_repo = ServerRepo(session)
    tariffs_repo = TariffRepo(session)

    sub_id = _extract_callback_id(callback.data, CB_SUB_PREFIX)
    if sub_id is None:
        await callback.answer(t("subs.invalid_id", lang), show_alert=True)
        return

    subscription = await subs_repo.get_by_id(sub_id)
    if subscription is None or subscription.user_id != user.id:
        await callback.answer(t("subs.not_found", lang), show_alert=True)
        return

    server = (
        await servers_repo.get_by_id_active(subscription.server_id)
        if subscription.server_id is not None
        else None
    )
    tariff = (
        await tariffs_repo.get_by_id_active(subscription.tariff_id)
        if subscription.tariff_id is not None
        else None
    )

    text = t(
        "subs.card_details",
        lang,
        **_build_subscription_card_context(subscription, server, tariff, lang),
    )

    await message.edit_text(text, reply_markup=subscription_card_kb(subscription, user))
    await callback.answer()


async def _extend_with_active_tariff(
    *,
    message: Message,
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    subscription: Subscription,
    server: Server,
    tariff: Tariff,
    lang: str,
) -> None:
    """Создаёт платёж на продление, когда у подписки есть активный тариф."""
    payment_service = PaymentService(session)

    metadata_snapshot = build_purchase_metadata(
        user=user,
        server=server,
        tariff=tariff,
        fsm_data={
            DATA_IS_EXTEND: True,
            DATA_EXTEND_SUBSCRIPTION_ID: subscription.id,
        },
    )

    idempotency_key = str(uuid.uuid4())
    try:
        payment = await payment_service.create_payment(
            user_id=user.id,
            amount=tariff.price_amount,
            currency=tariff.price_currency,
            provider=PaymentProvider.YOOKASSA,
            subscription_id=subscription.id,
            idempotency_key=idempotency_key,
            metadata_snapshot=metadata_snapshot,
        )
    except Exception:  # noqa: BLE001 — платёжный шлюз может кидать разные ошибки
        await callback.answer(t("purchase.create_failed", lang), show_alert=True)
        return

    # confirmation_url гарантирован PaymentService.create_payment() — см. там же.
    confirmation_url = cast("str", payment.confirmation_url)

    new_expires_at, new_data_limit_bytes = compute_extension(subscription, tariff)

    price = format_price(payment.amount, payment.currency)
    text = t(
        "purchase.extend_payment_created",
        lang,
        price=price,
        new_expires_at=format_date(new_expires_at),
        new_traffic=format_data_limit(new_data_limit_bytes),
    )
    await message.edit_text(
        text,
        reply_markup=payment_kb(payment.id, confirmation_url, user),
    )
    await callback.answer()


async def _extend_via_tariff_selection(
    *,
    message: Message,
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    server: Server,
    tariffs_repo: TariffRepo,
    lang: str,
) -> None:
    """Переводит пользователя в выбор нового тарифа для того же сервера."""
    await state.clear()
    await state.set_state(PurchaseStates.selecting_tariff)
    await state.update_data(build_purchase_data())
    await state.update_data({DATA_SERVER_ID: server.id})

    tariffs = await tariffs_repo.get_active_by_server(server.id)
    if not tariffs:
        await callback.answer(
            t("purchase.no_tariffs_for_server", lang), show_alert=True
        )
        await clear_purchase_state(state)
        return

    text = t("purchase.choose_tariff", lang)
    await message.edit_text(
        text,
        reply_markup=tariffs_kb(tariffs, user, back_callback=CB_MENU_MY_SUBS),
    )
    await callback.answer()


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_SUB_EXTEND}:")
)
async def on_subscription_extend(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """
    Продление подписки.
    Если у подписки есть активный тариф — сразу создаём платёж на продление.
    Если тариф недоступен — переводим пользователя в выбор тарифа для того же сервера.
    """
    message = _get_callback_message(callback)
    if message is None:
        await callback.answer()
        return

    lang = user.language_code or "ru"
    sub_id = _extract_callback_id(callback.data, CB_SUB_EXTEND)
    if sub_id is None:
        await callback.answer(t("subs.invalid_id", lang), show_alert=True)
        return

    subs_repo = SubscriptionRepo(session)
    tariffs_repo = TariffRepo(session)
    servers_repo = ServerRepo(session)

    subscription = await subs_repo.get_by_id(sub_id)
    if subscription is None or subscription.user_id != user.id:
        await callback.answer(t("subs.not_found", lang), show_alert=True)
        return

    if subscription.server_id is None:
        await callback.answer(t("subs.server_fallback", lang), show_alert=True)
        return

    tariff = None
    if subscription.tariff_id is not None:
        tariff = await tariffs_repo.get_by_id_active(subscription.tariff_id)

    server = await servers_repo.get_by_id_active(subscription.server_id)
    if server is None:
        await callback.answer(t("purchase.server_unavailable", lang), show_alert=True)
        return

    if tariff is not None:
        await _extend_with_active_tariff(
            message=message,
            callback=callback,
            session=session,
            user=user,
            subscription=subscription,
            server=server,
            tariff=tariff,
            lang=lang,
        )
        return

    await _extend_via_tariff_selection(
        message=message,
        callback=callback,
        state=state,
        user=user,
        server=server,
        tariffs_repo=tariffs_repo,
        lang=lang,
    )


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_SUB_HELP}:")
)
async def on_subscription_help(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """
    Краткая инструкция по подключению для конкретной подписки.
    Сейчас общий текст; позже можно делать его более детализированным.
    """
    message = _get_callback_message(callback)
    if message is None:
        await callback.answer()
        return

    lang = user.language_code or "ru"

    sub_id = _extract_callback_id(callback.data, CB_SUB_HELP)
    if sub_id is None:
        await callback.answer(t("subs.invalid_id", lang), show_alert=True)
        return

    _ = state
    _ = session
    _ = sub_id

    text = t("subs.help_text", lang)
    await message.edit_text(text, reply_markup=back_to_main_kb(user))
    await callback.answer()


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_SUB_LINK}:")
)
async def on_subscription_link(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    prepared = await _prepare_subscription_action(callback, session, user, CB_SUB_LINK)
    if prepared is None:
        return
    message, subscription = prepared

    lang = user.language_code or "ru"
    await message.answer(
        t("subs.link_message", lang, url=subscription.subscription_url)
    )
    await render_main_menu(message, user, session)
    await callback.answer()


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_SUB_QR}:")
)
async def on_subscription_qr(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    prepared = await _prepare_subscription_action(callback, session, user, CB_SUB_QR)
    if prepared is None:
        return
    message, subscription = prepared

    lang = user.language_code or "ru"
    qr_bytes = _make_qr_bytes(subscription.subscription_url)
    await message.answer_photo(
        BufferedInputFile(qr_bytes, filename="subscription_qr.png"),
        caption=t("subs.qr_caption", lang),
    )
    await render_main_menu(message, user, session)
    await callback.answer()


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_SUB_CONFIG_LINK}:")
)
async def on_subscription_config_link(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    prepared = await _prepare_subscription_action(
        callback, session, user, CB_SUB_CONFIG_LINK
    )
    if prepared is None:
        return
    message, subscription = prepared

    lang = user.language_code or "ru"
    config_link = await _get_marzban_config_link(subscription, lang, callback)
    if config_link is None:
        return

    await message.answer(t("subs.config_link_message", lang, url=config_link))
    await render_main_menu(message, user, session)
    await callback.answer()


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_SUB_CONFIG_QR}:")
)
async def on_subscription_config_qr(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    prepared = await _prepare_subscription_action(
        callback, session, user, CB_SUB_CONFIG_QR
    )
    if prepared is None:
        return
    message, subscription = prepared

    lang = user.language_code or "ru"
    config_link = await _get_marzban_config_link(subscription, lang, callback)
    if config_link is None:
        return

    qr_bytes = _make_qr_bytes(config_link)
    await message.answer_photo(
        BufferedInputFile(qr_bytes, filename="config_qr.png"),
        caption=t("subs.config_qr_caption", lang),
    )
    await render_main_menu(message, user, session)
    await callback.answer()
