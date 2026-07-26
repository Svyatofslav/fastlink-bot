from __future__ import annotations

import uuid

import structlog
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import PaymentProvider
from database.models import User
from database.repo.servers import ServerRepo
from database.repo.tariffs import TariffRepo
from keyboards.client import (
    CB_CONFIRM_PAY,
    CB_MENU_BACK_TO_TARIFFS,
    CB_MENU_BUY,
    CB_MENU_CANCEL,
    CB_SERVER_PREFIX,
    CB_TARIFF_PREFIX,
    confirm_purchase_kb,
    payment_kb,
    servers_kb,
    tariffs_kb,
    main_menu_kb,
)
from services.payment import PaymentService
from states.purchase import (
    DATA_IDEMPOTENCY_KEY,
    DATA_PAYMENT_IN_PROGRESS,
    DATA_SERVER_ID,
    DATA_TARIFF_ID,
    PurchaseStates,
    build_purchase_data,
    clear_purchase_state,
)
from utils.format import format_price
from utils.i18n import t
from domain.purchase_metadata import build_purchase_metadata

router = Router(name="client-purchase")
logger = structlog.get_logger(__name__)


@router.callback_query(lambda c: c.data == CB_MENU_BUY)
async def on_buy_clicked(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    servers_repo = ServerRepo(session)
    tariffs_repo = TariffRepo(session)

    servers = await servers_repo.get_active()
    lang = user.language_code or "ru"

    if not servers:
        await callback.answer(t("purchase.no_servers", lang), show_alert=True)
        return

    min_prices: dict[int, int] = {}
    for server in servers:
        tariffs = await tariffs_repo.get_active_by_server(server.id)
        if tariffs:
            min_prices[server.id] = min(tariff.price_amount for tariff in tariffs)

    await state.set_state(PurchaseStates.selecting_server)
    await state.update_data(build_purchase_data())

    await callback.message.edit_text(
        t("purchase.choose_server", lang),
        reply_markup=servers_kb(servers, min_prices, user),
    )
    await callback.answer()


async def _show_tariffs_for_server(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
    server_id: int,
) -> None:
    """
    Общая логика показа тарифов для конкретного сервера.
    Используется и при явном выборе сервера, и при возврате
    из экрана подтверждения назад к тарифам — без мутации callback.data.
    """
    servers_repo = ServerRepo(session)
    tariffs_repo = TariffRepo(session)

    lang = user.language_code or "ru"

    server = await servers_repo.get_by_id_active(server_id)
    if server is None:
        await callback.answer(t("purchase.server_unavailable", lang), show_alert=True)
        return

    tariffs = await tariffs_repo.get_active_by_server(server_id)
    if not tariffs:
        await callback.answer(
            t("purchase.no_tariffs_for_server", lang),
            show_alert=True,
        )
        return

    await state.update_data({DATA_SERVER_ID: server_id})
    await state.set_state(PurchaseStates.selecting_tariff)

    label = (server.emoji or server.name).strip()
    text = f"{label}\n{t('purchase.choose_tariff', lang)}"
    await callback.message.edit_text(
        text,
        reply_markup=tariffs_kb(tariffs, user, back_callback=CB_MENU_BUY),
    )
    await callback.answer()


@router.callback_query(
    PurchaseStates.selecting_server,
    lambda c: c.data.startswith(f"{CB_SERVER_PREFIX}"),
)
async def on_server_selected(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    server_id = int(callback.data.split(":")[1])
    await _show_tariffs_for_server(callback, session, state, user, server_id)


@router.callback_query(
    PurchaseStates.selecting_tariff,
    lambda c: c.data == CB_MENU_BUY,
)
async def on_back_to_servers(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    await on_buy_clicked(callback, session, state, user)


@router.callback_query(
    PurchaseStates.selecting_tariff,
    lambda c: c.data.startswith(f"{CB_TARIFF_PREFIX}"),
)
async def on_tariff_selected(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    tariff_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    server_id = data.get(DATA_SERVER_ID)

    servers_repo = ServerRepo(session)
    tariffs_repo = TariffRepo(session)

    lang = user.language_code or "ru"

    tariff = await tariffs_repo.get_by_id_active(tariff_id)
    server = await servers_repo.get_by_id_active(server_id) if server_id else None

    if tariff is None or server is None:
        await callback.answer(t("purchase.tariff_unavailable", lang), show_alert=True)
        return

    idempotency_key = str(uuid.uuid4())

    await state.update_data(
        {
            DATA_TARIFF_ID: tariff_id,
            DATA_IDEMPOTENCY_KEY: idempotency_key,
            DATA_PAYMENT_IN_PROGRESS: False,
        }
    )
    await state.set_state(PurchaseStates.confirming)

    price = format_price(tariff.price_amount, tariff.price_currency)
    text = t(
        "purchase.confirm_text",
        lang,
        server_label=server.emoji or server.name,
        tariff_name=tariff.name,
        price=price,
    )
    await callback.message.edit_text(text, reply_markup=confirm_purchase_kb(user))
    await callback.answer()


@router.callback_query(
    PurchaseStates.confirming,
    lambda c: c.data == CB_MENU_BACK_TO_TARIFFS,
)
async def on_back_to_tariffs(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    data = await state.get_data()
    server_id = data.get(DATA_SERVER_ID)
    lang = user.language_code or "ru"

    if server_id is None:
        await callback.answer(t("purchase.cannot_go_back", lang), show_alert=True)
        await clear_purchase_state(state)
        await callback.message.edit_text(
            t("main.menu.title", lang),
            reply_markup=main_menu_kb(user),
        )
        return

    await _show_tariffs_for_server(callback, session, state, user, server_id)


@router.callback_query(PurchaseStates.confirming, lambda c: c.data == CB_MENU_CANCEL)
async def on_cancel_purchase(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    lang = user.language_code or "ru"
    await clear_purchase_state(state)
    from keyboards.client import main_menu_kb

    await callback.message.edit_text(
        t("purchase.cancelled", lang),
        reply_markup=main_menu_kb(user),
    )
    await callback.answer()


@router.callback_query(
    PurchaseStates.confirming,
    lambda c: c.data == CB_CONFIRM_PAY,
)
async def on_confirm_pay(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    data = await state.get_data()
    lang = user.language_code or "ru"

    if data.get(DATA_PAYMENT_IN_PROGRESS):
        await callback.answer(
            t("purchase.payment_in_progress", lang),
            show_alert=True,
        )
        return

    await state.update_data({DATA_PAYMENT_IN_PROGRESS: True})

    server_id = data.get(DATA_SERVER_ID)
    tariff_id = data.get(DATA_TARIFF_ID)
    idempotency_key = data.get(DATA_IDEMPOTENCY_KEY)

    servers_repo = ServerRepo(session)
    tariffs_repo = TariffRepo(session)

    server = await servers_repo.get_by_id_active(server_id)
    tariff = await tariffs_repo.get_by_id_active(tariff_id)

    if server is None or tariff is None or idempotency_key is None:
        await callback.answer(t("purchase.data_expired", lang), show_alert=True)
        await clear_purchase_state(state)
        await callback.message.edit_text(
            t("main.menu.title", lang),
            reply_markup=main_menu_kb(user),
        )
        return

    metadata_snapshot = build_purchase_metadata(
        user=user,
        server=server,
        tariff=tariff,
        fsm_data=data,
    )

    payment_service = PaymentService(session)

    try:
        payment = await payment_service.create_payment(
            user_id=user.id,
            amount=tariff.price_amount,
            currency=tariff.price_currency,
            provider=PaymentProvider.YOOKASSA,
            subscription_id=None,
            idempotency_key=idempotency_key,
            metadata_snapshot=metadata_snapshot,
        )
    except Exception:
        logger.exception(
            "purchase_create_payment_failed",
            user_id=user.id,
            server_id=server.id,
            tariff_id=tariff.id,
        )
        await state.update_data({DATA_PAYMENT_IN_PROGRESS: False})
        await callback.answer(
            t("purchase.create_failed", lang),
            show_alert=True,
        )
        return

    await state.set_state(PurchaseStates.awaiting_payment)

    price = format_price(payment.amount, payment.currency)
    text = t("purchase.payment_created", lang, price=price)
    await callback.message.edit_text(
        text,
        reply_markup=payment_kb(payment.id, payment.confirmation_url, user),
    )
    await callback.answer()
