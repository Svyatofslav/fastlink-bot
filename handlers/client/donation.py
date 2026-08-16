from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from config import settings
from database.enums import PaymentProvider
from database.repo.users import UserRepo
from domain.donation_metadata import build_donation_metadata
from handlers.client.menu import render_main_menu
from keyboards.client import (
    CB_DONATION_CANCEL,
    CB_MENU_DONATE,
    donation_amount_kb,
    payment_kb,
)
from services.payment import PaymentService
from states.donation import DATA_DONATION_PAYMENT_IN_PROGRESS, DonationStates
from utils.format import format_price, parse_price
from utils.i18n import t
from utils.telegram import disable_previous_menu

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models import User

router = Router(name="client-donation")
logger = structlog.get_logger(__name__)


@router.callback_query(lambda c: c.data == CB_MENU_DONATE)
async def on_donate_clicked(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    lang = user.language_code or "ru"

    message = callback.message
    if message is None or not hasattr(message, "edit_text"):
        await callback.answer()
        return
    message = cast("Message", message)

    await state.set_state(DonationStates.waiting_for_amount)
    min_price = format_price(settings.donation_min_amount)
    max_price = format_price(settings.donation_max_amount)
    text = t("donation.ask_amount", lang, min_price=min_price, max_price=max_price)
    await message.edit_text(text, reply_markup=donation_amount_kb(user))
    await callback.answer()


@router.message(DonationStates.waiting_for_amount, F.text)
async def on_donation_amount_entered(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    user: User,
) -> None:
    lang = user.language_code or "ru"

    text = message.text
    if text is None:
        await message.answer(t("donation.invalid_amount", lang))
        return

    amount = parse_price(text)
    if amount is None:
        await message.answer(t("donation.invalid_amount", lang))
        return

    if amount < settings.donation_min_amount:
        await message.answer(
            t(
                "donation.amount_too_small",
                lang,
                min_price=format_price(settings.donation_min_amount),
            )
        )
        return

    if amount > settings.donation_max_amount:
        await message.answer(
            t(
                "donation.amount_too_large",
                lang,
                max_price=format_price(settings.donation_max_amount),
            )
        )
        return

    data = await state.get_data()
    if data.get(DATA_DONATION_PAYMENT_IN_PROGRESS):
        await message.answer(t("purchase.payment_in_progress", lang))
        return

    await state.update_data({DATA_DONATION_PAYMENT_IN_PROGRESS: True})

    idempotency_key = str(uuid.uuid4())
    metadata_snapshot = build_donation_metadata(
        user=user,
        amount=amount,
        currency="RUB",
    )

    payment_service = PaymentService(session)
    try:
        payment = await payment_service.create_payment(
            user_id=user.id,
            amount=amount,
            currency="RUB",
            provider=PaymentProvider.YOOKASSA,
            subscription_id=None,
            idempotency_key=idempotency_key,
            metadata_snapshot=metadata_snapshot,
        )
    except Exception:
        logger.exception(
            "donation_create_payment_failed",
            user_id=user.id,
            amount=amount,
        )
        await state.update_data({DATA_DONATION_PAYMENT_IN_PROGRESS: False})
        await message.answer(t("purchase.create_failed", lang))
        return

    # confirmation_url гарантирован PaymentService.create_payment() — см. там же.
    confirmation_url = cast("str", payment.confirmation_url)

    await state.set_state(DonationStates.awaiting_payment)

    # Гасим клавиатуру предыдущего сообщения ("Введите сумму доната...")
    # перед отправкой нового с кнопками оплаты — иначе старая кнопка "Отменить"
    # останется активной параллельно с новым меню.
    bot = message.bot
    if bot is not None:
        await disable_previous_menu(
            bot,
            message.chat.id,
            user.last_active_message_id,
        )

    price = format_price(payment.amount, payment.currency)
    text = t("donation.payment_created", lang, price=price)
    sent = await message.answer(
        text,
        reply_markup=payment_kb(payment.id, confirmation_url, user),
    )
    await UserRepo(session).set_last_active_message_id(user, sent.message_id)


@router.callback_query(lambda c: c.data == CB_DONATION_CANCEL)
async def on_donation_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    lang = user.language_code or "ru"

    message = callback.message
    if message is None or not isinstance(message, Message):
        await callback.answer()
        return

    await state.clear()
    await message.edit_text(t("purchase.cancelled", lang), reply_markup=None)
    await render_main_menu(message, user, session)
    await callback.answer()
