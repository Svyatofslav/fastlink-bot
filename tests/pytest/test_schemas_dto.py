from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from schemas.dto import NewSubscriptionParams


def test_new_subscription_params_rejects_naive_expires_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        NewSubscriptionParams(
            tariff_id=1,
            server_id=1,
            marzban_username="user1",
            expires_at=datetime(2026, 12, 31, 0, 0, 0),  # noqa: DTZ001 — намеренно naive, тестируем отклонение валидатором
        )


def test_new_subscription_params_accepts_aware_expires_at() -> None:
    params = NewSubscriptionParams(
        tariff_id=1,
        server_id=1,
        marzban_username="user1",
        expires_at=datetime(2026, 12, 31, tzinfo=UTC),
    )

    assert params.expires_at.tzinfo is not None
