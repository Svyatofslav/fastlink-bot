from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datetime import datetime

# Допустимые типы событий от YooKassa, которые мы обрабатываем.
# Полный список: https://yookassa.ru/developers/api#notification-object
YooKassaEvent = Literal[
    "payment.waiting_for_capture",
    "payment.succeeded",
    "payment.canceled",
    "payment.refunded",
    "refund.succeeded",
    "refund.failed",
]


class YooKassaAmount(BaseModel):
    value: str = Field(..., description="Сумма как строка, например '100.00'.")
    currency: str = Field(
        ..., min_length=3, max_length=3, description="Валюта, например 'RUB'."
    )


class YooKassaPaymentObject(BaseModel):
    """
    Модель payment-объекта YooKassa, урезанная до нужных полей.

    Полный JSON может быть больше, но мы фиксируем минимум, который нужен
    для бизнес-логики FastLink.
    """

    id: str = Field(
        ..., min_length=1, max_length=128, description="ID платежа в YooKassa."
    )
    status: str = Field(..., min_length=1, max_length=64, description="Статус платежа.")
    amount: YooKassaAmount
    paid: bool = Field(..., description="Флаг 'оплачен'.")
    created_at: datetime | None = Field(None, description="Время создания платежа.")
    description: str | None = Field(
        None, max_length=256, description="Описание платежа."
    )
    metadata: dict | None = Field(
        None,
        description="Произвольные метаданные, например subscription_id/user_id.",
    )


class YooKassaNotificationPayload(BaseModel):
    """
    Входной payload для webhook-уведомления от YooKassa.

    Источник: HTTP POST от YooKassa.
    Нормализуется ДО записи в WebhookEvent.payload.
    """

    event: YooKassaEvent = Field(
        ...,
        description="Тип события от YooKassa (payment.succeeded, payment.canceled, и т.д.).",
    )
    object: YooKassaPaymentObject
    # здесь можно добавить поля типа 'type', 'api_version' при необходимости
