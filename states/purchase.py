from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class PurchaseStates(StatesGroup):
    """Состояния сценария покупки/продления подписки.

    Один и тот же набор состояний используется как для обычной покупки,
    так и для продления (extend) — различие определяется флагом is_extend
    в данных состояния (state.update_data), а не отдельной StatesGroup.

    Хранится в Redis через RedisStorage (см. bot.py), поэтому данные
    переживают перезапуск бота и не теряются между сообщениями.
    """

    selecting_server = State()
    selecting_tariff = State()
    confirming = State()
    awaiting_payment = State()


# ---------------------------------------------------------------------------
# Ключи данных, которые хранятся в FSM-контексте (state.get_data() / update_data)
# Вынесены в константы, чтобы handlers не рассинхронизировались по строкам.
# ---------------------------------------------------------------------------
DATA_SERVER_ID = "server_id"
DATA_TARIFF_ID = "tariff_id"
DATA_IDEMPOTENCY_KEY = "idempotency_key"
DATA_PAYMENT_IN_PROGRESS = "payment_in_progress"
DATA_SUBSCRIPTION_ID = "subscription_id"
DATA_PAYMENT_ID = "payment_id"
DATA_IS_EXTEND = "is_extend"
DATA_EXTEND_SUBSCRIPTION_ID = "extend_subscription_id"


async def clear_purchase_state(state) -> None:
    """Полностью сбрасывает FSM-состояние покупки.

    Используется при отмене заказа, ошибке или успешном завершении цепочки,
    чтобы не оставлять "зависшие" server_id/tariff_id для следующей покупки.
    """
    await state.clear()


def build_extend_data(subscription_id: int) -> dict:
    """Формирует начальные данные состояния для сценария продления.

    Используется при входе в extend-flow из карточки подписки:
    state.set_state(PurchaseStates.selecting_tariff)
    await state.update_data(**build_extend_data(subscription_id))
    """
    return {
        DATA_IS_EXTEND: True,
        DATA_EXTEND_SUBSCRIPTION_ID: subscription_id,
    }


def build_purchase_data() -> dict:
    return {
        DATA_IS_EXTEND: False,
        DATA_EXTEND_SUBSCRIPTION_ID: None,
        DATA_SERVER_ID: None,
        DATA_TARIFF_ID: None,
        DATA_IDEMPOTENCY_KEY: None,
        DATA_PAYMENT_IN_PROGRESS: False,
    }
