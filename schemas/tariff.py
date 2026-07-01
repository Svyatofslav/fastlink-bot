from __future__ import annotations

from pydantic import BaseModel, Field


class TariffCreatePayload(BaseModel):
    """
    Входной payload для создания нового тарифа.

    Источник: форма в админке.
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Человекочитаемое имя тарифа.",
    )
    description: str | None = Field(
        None,
        max_length=512,
        description="Описание тарифа для пользователя.",
    )
    price_rub: int = Field(
        ...,
        ge=0,
        le=1_000_000,
        description="Стоимость тарифа в рублях.",
    )
    duration_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Длительность подписки в днях.",
    )
    data_limit_gb: int | None = Field(
        None,
        ge=1,
        le=10_000,
        description="Лимит трафика в ГБ или None для безлимита.",
    )
    server_id: int | None = Field(
        None,
        ge=0,
        description="Привязанный сервер или None для любого сервера.",
    )
    sort_order: int = Field(
        100,
        ge=0,
        le=10000,
        description="Порядок сортировки в списках.",
    )
    is_active: bool = Field(
        True,
        description="Флаг активности тарифа.",
    )


class TariffUpdatePayload(BaseModel):
    """
    Входной payload для обновления существующего тарифа.

    Все поля опциональны — меняем только то, что пришло.
    """

    name: str | None = Field(
        None,
        min_length=3,
        max_length=64,
        description="Новое имя тарифа или None.",
    )
    description: str | None = Field(
        None,
        max_length=512,
        description="Новое описание тарифа или None.",
    )
    price_rub: int | None = Field(
        None,
        ge=0,
        le=1_000_000,
        description="Новая стоимость в рублях или None.",
    )
    duration_days: int | None = Field(
        None,
        ge=1,
        le=365,
        description="Новая длительность в днях или None.",
    )
    data_limit_gb: int | None = Field(
        None,
        ge=1,
        le=10_000,
        description="Новый лимит трафика или None.",
    )
    server_id: int | None = Field(
        None,
        ge=0,
        description="Новый server_id или None.",
    )
    sort_order: int | None = Field(
        None,
        ge=0,
        le=10000,
        description="Новый порядок сортировки или None.",
    )
    is_active: bool | None = Field(
        None,
        description="True/False для смены активности или None.",
    )
