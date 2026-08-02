from __future__ import annotations

from typing import TYPE_CHECKING, cast

from aiogram import Router

from database.enums import PaymentStatus
from database.repo.payments import PaymentRepo
from keyboards.client import CB_PAYMENT_CANCEL, CB_PAYMENT_CHECK, main_menu_kb
from services.payment import PaymentService
from states.purchase import clear_purchase_state
from utils.format import format_price
from utils.i18n import t

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext
    from aiogram.types import CallbackQuery, Message
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models import User

router = Router(name="client-payment")


def _extract_payment_id(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(f"{prefix}:"):
        return None

    raw_payment_id = data.rsplit(":", 1)[-1]
    if not raw_payment_id.isdigit():
        return None

    return int(raw_payment_id)


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_PAYMENT_CHECK}:")
)
async def on_payment_check(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    payment_id = _extract_payment_id(callback.data, CB_PAYMENT_CHECK)
    lang = user.language_code or "ru"

    if payment_id is None:
        await callback.answer(t("payment.not_found", lang), show_alert=True)
        return

    payments_repo = PaymentRepo(session)
    payment = await payments_repo.get_by_id(payment_id)

    if payment is None:
        await callback.answer(t("payment.not_found", lang), show_alert=True)
        return

    message = callback.message
    if message is None:
        await callback.answer()
        return
    message = cast("Message", message)

    if payment.status == PaymentStatus.PENDING:
        await callback.answer(t("payment.pending", lang), show_alert=True)
        return

    if payment.status == PaymentStatus.SUCCEEDED:
        price = format_price(payment.amount, payment.currency)
        text = t("payment.succeeded.message", lang, price=price)
        await message.edit_reply_markup(reply_markup=None)
        await message.answer(text, reply_markup=main_menu_kb(user))
        await callback.answer()
        return

    if payment.status == PaymentStatus.CANCELED:
        await message.edit_text(
            t("payment.canceled.message", lang),
            reply_markup=main_menu_kb(user),
        )
        await callback.answer()
        return

    await callback.answer(f"Status: {payment.status.value}", show_alert=True)


@router.callback_query(
    lambda c: c.data is not None and c.data.startswith(f"{CB_PAYMENT_CANCEL}:")
)
async def on_payment_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    payment_id = _extract_payment_id(callback.data, CB_PAYMENT_CANCEL)
    lang = user.language_code or "ru"

    if payment_id is None:
        await callback.answer(t("payment.not_found", lang), show_alert=True)
        return

    payment_service = PaymentService(session)

    try:
        payment = await payment_service.cancel_pending_payment(payment_id=payment_id)
    except ValueError:
        await callback.answer(t("payment.not_found", lang), show_alert=True)
        return

    message = callback.message
    if message is None:
        await callback.answer()
        return
    message = cast("Message", message)

    if payment.status != PaymentStatus.CANCELED:
        await callback.answer(t("payment.cancel_impossible", lang), show_alert=True)
        return

    await clear_purchase_state(state)
    await message.edit_text(
        t("payment.canceled.message", lang),
        reply_markup=main_menu_kb(user),
    )
    await callback.answer()
