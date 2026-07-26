from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SubscriptionSummary(BaseModel):
    """
    DTO для краткого описания подписки, используемого в сервисах/handler’ах.

    Не является прямым ORM-объектом — только нормализованные данные.
    """

    id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0)
    server_id: int = Field(..., gt=0)
    tariff_id: int = Field(..., gt=0)
    status: str = Field(..., min_length=1, max_length=32)
    created_at: datetime
    expires_at: datetime | None
    data_limit_bytes: int | None
    data_used_bytes: int


class ServerLoadDTO(BaseModel):
    """
    DTO для нагрузки сервера, полученной через MetricsClient.

    Используется NotificationService/SubscriptionService.
    """

    server_id: int = Field(..., gt=0)
    cpu_usage_percent: float = Field(..., ge=0.0, le=100.0)
    memory_usage_percent: float = Field(..., ge=0.0, le=100.0)
    bandwidth_mbps: float = Field(..., ge=0.0)
    active_users_count: int = Field(..., ge=0)


class NotificationTaskDTO(BaseModel):
    """
    DTO для задания на отправку уведомления пользователю.

    Содержит уже нормализованные данные, без сырых ORM-объектов.
    """

    user_id: int = Field(..., gt=0)
    subscription_id: int | None = Field(None, gt=0)
    type: str = Field(..., min_length=1, max_length=64)
    payload: dict | None = Field(
        None,
        description="Произвольные данные для шаблона уведомления.",
    )


class NewSubscriptionParams(BaseModel):
    """DTO для создания Subscription внутри PaymentService.process_successful_payment.

    Строится из metadata_snapshot платежа (scheduler/jobs/__init__.py:
    build_new_subscription_params). Валидация здесь защищает от кривых
    данных, случайно попавших в JSONB-снэпшот вебхука.
    """

    model_config = {"frozen": True}

    tariff_id: int = Field(..., gt=0)
    server_id: int = Field(..., gt=0)
    marzban_username: str = Field(..., min_length=1, max_length=128)
    starts_at: datetime | None = None
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return v
