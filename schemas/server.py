from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class ServerCreatePayload(BaseModel):
    """
    Входной payload для создания нового VPN-сервера.

    Источник: форма в админке.
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Человекочитаемое имя сервера (для админки).",
    )
    api_url: HttpUrl = Field(
        ...,
        description="Базовый URL Marzban API, например https://host:8000/api.",
    )
    inbound_tag: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Inbound tag для Marzban (маршрутизация трафика).",
    )
    sort_order: int = Field(
        100,
        ge=0,
        le=10000,
        description="Порядок сортировки в списках (меньше — выше).",
    )
    is_active: bool = Field(
        True,
        description="Флаг активности сервера (виден ли пользователям).",
    )


class ServerUpdatePayload(BaseModel):
    """
    Входной payload для обновления существующего VPN-сервера.

    Все поля опциональны — меняем только то, что пришло.
    """

    name: str | None = Field(
        None,
        min_length=3,
        max_length=64,
        description="Новое имя сервера или None, если не менять.",
    )
    api_url: HttpUrl | None = Field(
        None,
        description="Новый базовый URL Marzban API или None, если не менять.",
    )
    inbound_tag: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        description="Новый inbound tag или None, если не менять.",
    )
    sort_order: int | None = Field(
        None,
        ge=0,
        le=10000,
        description="Новый порядок сортировки или None.",
    )
    is_active: bool | None = Field(
        None,
        description="True/False для смены статуса или None, если не менять.",
    )


class ServerTokensUpdatePayload(BaseModel):
    """
    Входной payload для установки/очистки токенов сервера.

    API/metrics токены валидируются и нормализуются ДО ServerRepo.set_server_tokens.
    """

    api_token: str | None = Field(
        None,
        min_length=16,
        max_length=256,
        description="Новый Marzban API token или None для очистки.",
    )
    metrics_token: str | None = Field(
        None,
        min_length=16,
        max_length=256,
        description="Новый metrics-agent Bearer token или None для очистки.",
    )
