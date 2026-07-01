from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, SecretStr


class AdminLoginPayload(BaseModel):
    """
    Входной payload для попытки логина админа.

    Источник: форма/команда в админке (Telegram или веб).
    Нормализуется ДО передачи в AdminAuthService.verify_login.
    """

    login: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Уникальный логин админа.",
    )
    password: SecretStr = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Пароль в открытом виде, минимум 8 символов.",
    )


class AdminCreatePayload(BaseModel):
    """
    Входной payload для создания нового админа.

    Источник: форма создания админа в админке.
    Нормализуется ДО вызова AdminAuthService.create_admin_with_plain_password.
    """

    telegram_id: int = Field(
        ...,
        gt=0,
        description="Telegram user ID будущего админа.",
    )
    username: str | None = Field(
        None,
        max_length=32,
        description="Telegram username (@username) без @, опционально.",
    )
    login: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Уникальный логин админа (используется для входа).",
    )
    password: SecretStr = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Пароль в открытом виде.",
    )
    secret_word: SecretStr = Field(
        ...,
        min_length=4,
        max_length=64,
        description="Секретное слово для дополнительной проверки.",
    )
    is_superadmin: bool = Field(
        False,
        description="Флаг супер-админа. True даёт расширенные права.",
    )
    created_by_admin_id: int | None = Field(
        None,
        gt=0,
        description="ID админа, который создаёт нового (для аудита).",
    )


class AdminProfileUpdatePayload(BaseModel):
    """
    Входной payload для обновления профиля админа (не безопасности).

    Источник: форма редактирования в админке.
    """

    username: str | None = Field(
        None,
        max_length=32,
        description="Новый Telegram username или None, если не менять.",
    )
    login: str | None = Field(
        None,
        min_length=3,
        max_length=64,
        description="Новый логин админа или None, если не менять.",
    )
    email: EmailStr | None = Field(
        None,
        description="Опциональный email для уведомлений и восстановления.",
    )


class AdminStatusChangePayload(BaseModel):
    """
    Входной payload для смены статуса админа (активен/заблокирован).

    Источник: действие в админке.
    """

    admin_id: int = Field(
        ...,
        gt=0,
        description="ID админа, чей статус меняется.",
    )
    active: bool = Field(
        ...,
        description="True — активировать, False — деактивировать.",
    )
    reason: str | None = Field(
        None,
        max_length=255,
        description="Причина изменения статуса (для логов).",
    )


class AdminAuthResult(BaseModel):
    """
    DTO-результат успешной аутентификации админа.

    Используется как контракт между AdminAuthService и handler’ами.
    """

    admin_id: int = Field(..., gt=0)
    telegram_id: int = Field(..., gt=0)
    login: str = Field(..., min_length=3, max_length=64)
    is_superadmin: bool
    appenv: Literal["development", "production", "test"] | None = Field(
        None,
        description="Среда, в которой выполнен логин (для UI/логирования).",
    )
