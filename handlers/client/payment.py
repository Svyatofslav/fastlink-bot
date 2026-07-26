from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import PaymentStatus
from database.models import User  # NEW
from database.repo.payments import PaymentRepo
from keyboards.client import CB_PAYMENT_CANCEL, CB_PAYMENT_CHECK, main_menu_kb
from services.payment import PaymentService
from states.purchase import clear_purchase_state
from utils.format import format_price
from utils.i18n import t  # NEW

router = Router(name="client-payment")


@router.callback_query(lambda c: c.data.startswith(f"{CB_PAYMENT_CHECK}:"))
async def on_payment_check(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,  # NEW
) -> None:
    payment_id = int(callback.data.split(":")[-1])
    payments_repo = PaymentRepo(session)
    payment = await payments_repo.get_by_id(payment_id)

    lang = user.language_code or "ru"

    if payment is None:
        await callback.answer(t("payment.not_found", lang), show_alert=True)
        return

    if payment.status == PaymentStatus.PENDING:
        await callback.answer(t("payment.pending", lang), show_alert=True)
        return

    if payment.status == PaymentStatus.SUCCEEDED:
        price = format_price(payment.amount, payment.currency)
        text = t("payment.succeeded.message", lang, price=price)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(text, reply_markup=main_menu_kb(user))
        await callback.answer()
        return

    if payment.status == PaymentStatus.CANCELED:
        await callback.message.edit_text(
            t("payment.canceled.message", lang),
            reply_markup=main_menu_kb(user),
        )
        await callback.answer()
        return

    # Для редких статусов можно показать raw value (на английском обычно).
    await callback.answer(f"Status: {payment.status.value}", show_alert=True)


@router.callback_query(lambda c: c.data.startswith(f"{CB_PAYMENT_CANCEL}:"))
async def on_payment_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    payment_id = int(callback.data.split(":")[-1])
    lang = user.language_code or "ru"
    payment_service = PaymentService(session)

    try:
        payment = await payment_service.cancel_pending_payment(payment_id=payment_id)
    except ValueError:
        await callback.answer(t("payment.not_found", lang), show_alert=True)
        return

    if payment.status != PaymentStatus.CANCELED:
        await callback.answer(t("payment.cancel_impossible", lang), show_alert=True)
        return

    await clear_purchase_state(state)
    await callback.message.edit_text(
        t("payment.canceled.message", lang),
        reply_markup=main_menu_kb(user),
    )
    await callback.answer()
