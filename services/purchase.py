from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from schemas.dto import NewSubscriptionParams

if TYPE_CHECKING:
    from database.models import Server, Tariff, User


def generate_marzban_username(telegram_id: int) -> str:
    """
    Генерирует уникальный username для Marzban на основе telegram_id.

    Формат: fl_<telegram_id>_<8 hex chars>.
    Вынесено отдельно, чтобы можно было протестировать формат
    и уникальность без обращения к БД или Marzban API.
    """
    return f"fl_{telegram_id}_{uuid.uuid4().hex[:8]}"


def build_purchase_metadata(
    *,
    tariff: Tariff,
    server: Server,
    user: User,
    now: datetime | None = None,
) -> dict:
    """
    Собирает metadata_snapshot для Payment при обычной покупке (не extend).

    Результат кладётся в Payment.metadata_snapshot и позже используется
    в scheduler/jobs при обработке payment.succeeded для создания
    Subscription через NewSubscriptionParams (см. build_new_subscription_params
    в schedulerjobs/__init__.py).

    Вынесено в чистую функцию без сессии БД и без сети, чтобы:
    - юнит-тестировать генерацию marzban_username и расчёт expires_at изолированно;
    - не размазывать бизнес-логику подготовки данных по хендлеру aiogram.
    """
    now = now or datetime.now(UTC)
    expires_at = now + timedelta(days=tariff.duration_days)
    marzban_username = generate_marzban_username(user.telegram_id)

    return {
        "tariff_id": tariff.id,
        "server_id": server.id,
        "marzban_username": marzban_username,
        "starts_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "type": "purchase",
    }


def build_new_subscription_params_preview(
    *,
    tariff: Tariff,
    server: Server,
    user: User,
    now: datetime | None = None,
) -> NewSubscriptionParams:
    """
    То же самое, что build_purchase_metadata, но сразу возвращает
    провалидированный NewSubscriptionParams — удобно для юнит-тестов,
    которые проверяют, что данные пройдут валидацию Pydantic
    (например, что expires_at timezone-aware).
    """
    metadata = build_purchase_metadata(tariff=tariff, server=server, user=user, now=now)
    return NewSubscriptionParams.model_validate(metadata)
