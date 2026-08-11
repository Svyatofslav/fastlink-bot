from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.models import Subscription, Tariff


def compute_extension(
    subscription: Subscription, tariff: Tariff, *, now: datetime | None = None
) -> tuple[datetime, int]:
    """
    Считает новые expires_at и data_limit_bytes при продлении подписки тем же тарифом.

    - expires_at: сдвигается на tariff.duration_days от max(текущий expires_at, now),
      чтобы не терять уже оплаченные дни при продлении заранее и не начислять их
      "в прошлое", если подписка уже истекла.
    - data_limit_bytes: остаток текущего лимита + лимит нового периода тарифа.
      Работает одинаково для лимитированных и безлимитных (0) тарифов, так как
      тариф при продлении не меняется (0 + 0 = 0).
    """
    now = now or datetime.now(UTC)
    base = (
        subscription.expires_at
        if subscription.expires_at and subscription.expires_at > now
        else now
    )
    new_expires_at = base + timedelta(days=tariff.duration_days)
    new_data_limit_bytes = subscription.data_limit_bytes + tariff.data_limit_bytes
    return new_expires_at, new_data_limit_bytes
