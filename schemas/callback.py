from __future__ import annotations

from pydantic import BaseModel, Field


class BaseCallbackPayload(BaseModel):
    """
    Базовый payload для callback_data.

    Все конкретные payload’ы наследуются от него.
    """

    action: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Тип действия, зашитый в callback_data.",
    )


class SubscriptionActionCallbackPayload(BaseCallbackPayload):
    """
    Payload для действий по подписке, например:
    - отключение/включение
    - запрос возврата
    """

    subscription_id: int = Field(
        ...,
        gt=0,
        description="ID подписки, над которой выполняется действие.",
    )


class TariffSelectCallbackPayload(BaseCallbackPayload):
    """
    Payload для выбора тарифа пользователем.

    Например: action='tariff_select', tariff_id=<id>.
    """

    tariff_id: int = Field(
        ...,
        gt=0,
        description="ID выбранного тарифа.",
    )


class AdminMenuCallbackPayload(BaseCallbackPayload):
    """
    Payload для навигации по админскому меню.

    Например: action='admin_menu', section='servers'/'tariffs'/... .
    """

    section: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Секция админского меню.",
    )
