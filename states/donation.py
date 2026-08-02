from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.fsm.state import State, StatesGroup

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext


class DonationStates(StatesGroup):
    waiting_for_amount = State()
    awaiting_payment = State()


DATA_DONATION_IDEMPOTENCY_KEY = "donation_idempotency_key"
DATA_DONATION_PAYMENT_IN_PROGRESS = "donation_payment_in_progress"


async def clear_donation_state(state: FSMContext) -> None:
    await state.clear()
