from __future__ import annotations

from pydantic import BaseModel, Field


class ServerCreatePayload(BaseModel):
    """
    Входной payload для создания нового VPN-сервера (локации).

    Источник: форма в админке.
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Человекочитаемое имя сервера (для админки).",
    )
    marzban_node_id: int = Field(
        ...,
        description="ID ноды в панели-мастере Marzban (Node Settings).",
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
    marzban_node_id: int | None = Field(
        None,
        description="Новый ID ноды в панели-мастере Marzban или None, если не менять.",
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
    Входной payload для установки/очистки metrics-токена сервера.

    Marzban API токен больше не хранится per-server — используется
    единая панель-мастер (Settings.marzban_*). Только metrics-agent
    токен остаётся per-server.
    """

    metrics_token: str | None = Field(
        None,
        min_length=16,
        max_length=256,
        description="Новый metrics-agent Bearer token или None для очистки.",
    )
