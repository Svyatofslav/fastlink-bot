from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from schemas.dto import NewSubscriptionParams
from states.purchase import DATA_EXTEND_SUBSCRIPTION_ID, DATA_IS_EXTEND

if TYPE_CHECKING:
    from database.models import Server, Tariff, User


def build_subscription_dates(*, duration_days: int) -> tuple[datetime | None, datetime]:
    """
    Высчитывает starts_at/expires_at для новой подписки.
    Сейчас можно считать starts_at=now, expires_at=now+duration_days.
    Позже, если логика изменится (например, starts_at при первой активации),
    мы поменяем только этот helper.
    """
    now = datetime.now(UTC)
    starts_at = now
    expires_at = now + timedelta(days=duration_days)
    return starts_at, expires_at


def build_purchase_metadata(
    *,
    user: User,
    server: Server,
    tariff: Tariff,
    fsm_data: dict,
) -> dict:
    """
    Собирает metadata_snapshot для платежа из ORM-объектов и FSM-данных.
    fsm_data — это state.get_data() в момент подтверждения покупки.

    ВАЖНО: эта вложенная структура предназначена ТОЛЬКО для хранения
    в Payment.metadata_snapshot (аудит, отладка, админка).
    Для передачи в YooKassa API используй build_yookassa_flat_metadata(),
    так как сама YooKassa поддерживает только плоский metadata
    (строка -> строка/число, максимум 16 пар ключ-значение).
    """
    starts_at, expires_at = build_subscription_dates(
        duration_days=tariff.duration_days,
    )

    is_extend = bool(fsm_data.get(DATA_IS_EXTEND))
    extend_subscription_id = fsm_data.get(DATA_EXTEND_SUBSCRIPTION_ID)

    # Простейший генератор marzban_username — можно позже вынести в отдельный helper
    marzban_username = f"fastlink_{user.id}_{int(expires_at.timestamp())}"

    return {
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
        },
        "server": {
            "id": server.id,
            "name": server.name,
            "emoji": server.emoji,
            "marzban_node_id": server.marzban_node_id,
            "inbound_tag": server.inbound_tag,
        },
        "tariff": {
            "id": tariff.id,
            "name": tariff.name,
            "duration_days": tariff.duration_days,
            "data_limit_bytes": tariff.data_limit_bytes,
            "price_amount": tariff.price_amount,
            "price_currency": tariff.price_currency,
        },
        "subscription": {
            "marzban_username": marzban_username,
            "starts_at": starts_at.isoformat() if starts_at is not None else None,
            "expires_at": expires_at.isoformat(),
        },
        "flags": {
            "is_extend": is_extend,
            "extend_subscription_id": extend_subscription_id,
        },
    }


def build_new_subscription_params_from_metadata(
    metadata: dict,
) -> NewSubscriptionParams:
    """
    Конвертирует вложенный metadata_snapshot платежа в NewSubscriptionParams.
    Ожидает структуру, которую строит build_purchase_metadata.

    Используется только для ручных/административных сценариев
    (например, пересборка подписки из Payment.metadata_snapshot в админке).
    В реальном webhook-пайплайне (scheduler/jobs) НЕ используется:
    там разбор идёт из плоского metadata, полученного напрямую от YooKassa,
    через _build_new_subscription_params.
    """
    server = metadata["server"]
    tariff = metadata["tariff"]
    subscription = metadata["subscription"]

    expires_at = datetime.fromisoformat(subscription["expires_at"])
    starts_at_raw = subscription.get("starts_at")
    starts_at = datetime.fromisoformat(starts_at_raw) if starts_at_raw else None

    return NewSubscriptionParams(
        tariff_id=tariff["id"],
        server_id=server["id"],
        marzban_username=subscription["marzban_username"],
        starts_at=starts_at,
        expires_at=expires_at,
    )


def build_yookassa_flat_metadata(metadata: dict) -> dict[str, str]:
    """
    Строит ПЛОСКИЙ metadata для передачи в YooKassa API при создании платежа.

    Это тот самый metadata, который YooKassa вернёт в webhook payment.succeeded
    в поле object.metadata, и который разбирает
    scheduler/jobs/_build_new_subscription_params.

    Обязательные ключи для новой подписки: tariff_id, server_id,
    marzban_username, expires_at. Опционально: starts_at, subscription_id
    (последний — для сценария продления существующей подписки).

    YooKassa поддерживает только плоские строковые пары ключ-значение
    (максимум 16 пар, до 512 символов каждая), поэтому вложенный
    metadata_snapshot передавать напрямую нельзя.
    """
    server = metadata["server"]
    tariff = metadata["tariff"]
    subscription = metadata["subscription"]
    flags = metadata["flags"]

    flat: dict[str, str] = {
        "tariff_id": str(tariff["id"]),
        "server_id": str(server["id"]),
        "marzban_username": subscription["marzban_username"],
        "expires_at": subscription["expires_at"],
    }

    if subscription.get("starts_at"):
        flat["starts_at"] = subscription["starts_at"]

    if flags.get("is_extend") and flags.get("extend_subscription_id"):
        flat["subscription_id"] = str(flags["extend_subscription_id"])

    return flat
