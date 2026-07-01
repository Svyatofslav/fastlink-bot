from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RefundRequestCreatePayload(BaseModel):
    """
    Входной payload для создания запроса на возврат.

    Источник: пользовательский ввод (бот/веб).
    Нормализуется ДО записи в таблицу refund_requests.
    """

    user_id: int = Field(
        ...,
        gt=0,
        description="ID пользователя, который инициирует возврат.",
    )
    subscription_id: int = Field(
        ...,
        gt=0,
        description="ID подписки, по которой запрашивается возврат.",
    )
    reason: str = Field(
        ...,
        min_length=4,
        max_length=1024,
        description="Текстовая причина возврата, как её указал пользователь.",
    )
    requested_amount_rub: int | None = Field(
        None,
        ge=0,
        le=1_000_000,
        description="Запрошенная сумма возврата в рублях (опционально).",
    )


class RefundRequestReviewPayload(BaseModel):
    """
    Входной payload для ревью запроса на возврат админом.

    Источник: действие админа в админке.
    """

    refund_request_id: int = Field(
        ...,
        gt=0,
        description="ID запроса на возврат.",
    )
    approved: bool = Field(
        ...,
        description="True — одобрить, False — отклонить.",
    )
    admin_comment: str | None = Field(
        None,
        max_length=1024,
        description="Комментарий админа к решению.",
    )


class RefundProcessPayload(BaseModel):
    """
    Входной payload для запуска фактического возврата (через YooKassa).

    Источник: внутренний сервис/worker.
    """

    refund_request_id: int = Field(..., gt=0)
    payment_id: int = Field(..., gt=0)
    amount_rub: int = Field(
        ...,
        ge=1,
        le=1_000_000,
        description="Сумма возврата в рублях.",
    )
    processed_at: datetime | None = Field(
        None,
        description="Время начала обработки (для учёта в логах).",
    )
