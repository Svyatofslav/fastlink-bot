from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from database.enums import (
    AdminActionType,
    DisabledReason,
    RefundRequestStatus,
    RefundStatus,
)
from services.refund import RefundService


class _AsyncCM:
    """Заглушка для `async with self._session.begin_nested(): ...`."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False


def make_service() -> tuple[RefundService, dict[str, MagicMock]]:
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=_AsyncCM())
    session.flush = AsyncMock()

    mocks = {
        "refund_requests": MagicMock(),
        "refunds": MagicMock(),
        "payments": MagicMock(),
        "notifications": MagicMock(),
        "subscriptions": MagicMock(),
        "admin_actions": MagicMock(),
    }
    with (
        patch(
            "services.refund.RefundRequestRepo", return_value=mocks["refund_requests"]
        ),
        patch("services.refund.RefundRepo", return_value=mocks["refunds"]),
        patch("services.refund.PaymentRepo", return_value=mocks["payments"]),
        patch(
            "services.refund.NotificationService", return_value=mocks["notifications"]
        ),
        patch(
            "services.refund.SubscriptionService", return_value=mocks["subscriptions"]
        ),
        patch(
            "services.refund.AdminActionLogService", return_value=mocks["admin_actions"]
        ),
    ):
        service = RefundService(session)
    return service, mocks


# ---------------------------------------------------------------------------
# create_refund_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_refund_request_delegates_with_new_status() -> None:
    service, mocks = make_service()
    created = SimpleNamespace(id=1)
    mocks["refund_requests"].create = AsyncMock(return_value=created)

    result = await service.create_refund_request(
        user_id=1, payment_id=2, subscription_id=3, reason="not needed anymore"
    )

    assert result is created
    mocks["refund_requests"].create.assert_awaited_once_with(
        user_id=1,
        payment_id=2,
        subscription_id=3,
        reason="not needed anymore",
        status=RefundRequestStatus.NEW,
        admin_comment=None,
        reviewed_by_admin_id=None,
        reviewed_at=None,
    )


# ---------------------------------------------------------------------------
# set_request_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_request_status_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["refund_requests"].get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await service.set_request_status(
            refund_request_id=999, status=RefundRequestStatus.APPROVED
        )


@pytest.mark.asyncio
async def test_set_request_status_without_admin_id_skips_audit() -> None:
    service, mocks = make_service()
    existing = SimpleNamespace(id=1, admin_comment=None, status=RefundRequestStatus.NEW)
    mocks["refund_requests"].get_by_id = AsyncMock(return_value=existing)
    updated = SimpleNamespace(
        id=1, status=RefundRequestStatus.APPROVED, admin_comment=None
    )
    mocks["refund_requests"].set_status = AsyncMock(return_value=updated)

    result = await service.set_request_status(
        refund_request_id=1, status=RefundRequestStatus.APPROVED, admin_id=None
    )

    assert result is updated
    mocks["refund_requests"].set_status.assert_awaited_once_with(
        existing,
        status=RefundRequestStatus.APPROVED,
        admin_comment=None,
        reviewed_by_admin_id=None,
        reviewed_at=None,
    )
    mocks["admin_actions"].log_action.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_action"),
    [
        (RefundRequestStatus.APPROVED, AdminActionType.APPROVE_REFUND),
        (RefundRequestStatus.REJECTED, AdminActionType.REJECT_REFUND),
        (RefundRequestStatus.PROCESSED, AdminActionType.PROCESS_REFUND),
        (RefundRequestStatus.FAILED, AdminActionType.PROCESS_REFUND),
    ],
)
async def test_set_request_status_with_admin_id_logs_correct_action(
    status: RefundRequestStatus, expected_action: AdminActionType
) -> None:
    service, mocks = make_service()
    existing = SimpleNamespace(id=1, admin_comment=None, status=RefundRequestStatus.NEW)
    mocks["refund_requests"].get_by_id = AsyncMock(return_value=existing)
    updated = SimpleNamespace(id=1, status=status, admin_comment="ok")
    mocks["refund_requests"].set_status = AsyncMock(return_value=updated)
    mocks["admin_actions"].log_action = AsyncMock()

    await service.set_request_status(
        refund_request_id=1, status=status, admin_id=42, admin_comment="ok"
    )

    mocks["admin_actions"].log_action.assert_awaited_once()
    call_kwargs = mocks["admin_actions"].log_action.await_args.kwargs
    assert call_kwargs["admin_id"] == 42
    assert call_kwargs["action"] == expected_action
    assert call_kwargs["entity_id"] == updated.id


@pytest.mark.asyncio
async def test_set_request_status_with_admin_id_no_mapped_action_skips_audit() -> None:
    service, mocks = make_service()
    existing = SimpleNamespace(id=1, admin_comment=None, status=RefundRequestStatus.NEW)
    mocks["refund_requests"].get_by_id = AsyncMock(return_value=existing)
    updated = SimpleNamespace(
        id=1, status=RefundRequestStatus.IN_REVIEW, admin_comment=None
    )
    mocks["refund_requests"].set_status = AsyncMock(return_value=updated)

    await service.set_request_status(
        refund_request_id=1, status=RefundRequestStatus.IN_REVIEW, admin_id=42
    )

    mocks["admin_actions"].log_action.assert_not_called()


# ---------------------------------------------------------------------------
# _resolve_refund_after_race
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_refund_after_race_finds_by_provider_refund_id() -> None:
    service, mocks = make_service()
    found = SimpleNamespace(id=5)
    mocks["refunds"].get_by_provider_refund_id = AsyncMock(return_value=found)

    result = await service._resolve_refund_after_race(
        refund_request_id=1, provider_refund_id="yk-1"
    )

    assert result is found
    mocks["refunds"].get_by_refund_request.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_refund_after_race_falls_back_when_not_found_by_provider_id() -> (
    None
):
    service, mocks = make_service()
    mocks["refunds"].get_by_provider_refund_id = AsyncMock(return_value=None)
    fallback = SimpleNamespace(id=7)
    mocks["refunds"].get_by_refund_request = AsyncMock(return_value=[fallback])

    result = await service._resolve_refund_after_race(
        refund_request_id=1, provider_refund_id="yk-missing"
    )

    assert result is fallback


@pytest.mark.asyncio
async def test_resolve_refund_after_race_no_provider_id_skips_first_lookup() -> None:
    service, mocks = make_service()
    fallback = SimpleNamespace(id=9)
    mocks["refunds"].get_by_refund_request = AsyncMock(return_value=[fallback])

    result = await service._resolve_refund_after_race(
        refund_request_id=1, provider_refund_id=None
    )

    assert result is fallback
    mocks["refunds"].get_by_provider_refund_id.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_refund_after_race_returns_none_when_nothing_found() -> None:
    service, mocks = make_service()
    mocks["refunds"].get_by_provider_refund_id = AsyncMock(return_value=None)
    mocks["refunds"].get_by_refund_request = AsyncMock(return_value=[])

    result = await service._resolve_refund_after_race(
        refund_request_id=1, provider_refund_id="yk-1"
    )

    assert result is None


# ---------------------------------------------------------------------------
# create_refund_for_request — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_refund_for_request_request_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["refund_requests"].get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match=r"RefundRequest .* not found"):
        await service.create_refund_for_request(
            refund_request_id=999, amount=1000, currency="RUB"
        )


@pytest.mark.asyncio
async def test_create_refund_for_request_payment_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["refund_requests"].get_by_id = AsyncMock(
        return_value=SimpleNamespace(id=1, payment_id=42)
    )
    mocks["refunds"].get_by_refund_request = AsyncMock(return_value=[])
    mocks["payments"].get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Payment 42 not found"):
        await service.create_refund_for_request(
            refund_request_id=1, amount=1000, currency="RUB"
        )


@pytest.mark.asyncio
async def test_create_refund_for_request_race_resolves_to_existing() -> None:
    service, mocks = make_service()
    mocks["refund_requests"].get_by_id = AsyncMock(
        return_value=SimpleNamespace(id=1, payment_id=42)
    )
    mocks["refunds"].get_by_refund_request = AsyncMock(return_value=[])
    payment = SimpleNamespace(id=42, amount=10000, provider="yookassa")
    mocks["payments"].get_by_id = AsyncMock(return_value=payment)
    mocks["refunds"].get_by_payment = AsyncMock(return_value=[])
    mocks["refunds"].create = AsyncMock(side_effect=IntegrityError("dup", None, None))
    existing_after_race = SimpleNamespace(id=100)

    with patch.object(
        service,
        "_resolve_refund_after_race",
        new=AsyncMock(return_value=existing_after_race),
    ):
        result = await service.create_refund_for_request(
            refund_request_id=1, amount=5000, currency="RUB"
        )

    assert result is existing_after_race


@pytest.mark.asyncio
async def test_create_refund_for_request_race_unresolved_reraises() -> None:
    service, mocks = make_service()
    mocks["refund_requests"].get_by_id = AsyncMock(
        return_value=SimpleNamespace(id=1, payment_id=42)
    )
    mocks["refunds"].get_by_refund_request = AsyncMock(return_value=[])
    payment = SimpleNamespace(id=42, amount=10000, provider="yookassa")
    mocks["payments"].get_by_id = AsyncMock(return_value=payment)
    mocks["refunds"].get_by_payment = AsyncMock(return_value=[])
    mocks["refunds"].create = AsyncMock(side_effect=IntegrityError("dup", None, None))

    with (
        patch.object(
            service, "_resolve_refund_after_race", new=AsyncMock(return_value=None)
        ),
        pytest.raises(IntegrityError),
    ):
        await service.create_refund_for_request(
            refund_request_id=1, amount=5000, currency="RUB"
        )


# ---------------------------------------------------------------------------
# _check_idempotent_or_stale — terminal state transition branch
# ---------------------------------------------------------------------------


def test_check_idempotent_or_stale_terminal_state_mismatch_returns_true() -> None:
    service, _mocks = make_service()
    refund = SimpleNamespace(id=1, status=RefundStatus.SUCCEEDED, completed_at=None)

    result = service._check_idempotent_or_stale(
        refund, RefundStatus.CANCELED, "yk-refund-1"
    )

    assert result is True


def test_check_idempotent_or_stale_active_status_returns_false() -> None:
    service, _mocks = make_service()
    refund = SimpleNamespace(id=1, status=RefundStatus.PENDING, completed_at=None)

    result = service._check_idempotent_or_stale(
        refund, RefundStatus.SUCCEEDED, "yk-refund-1"
    )

    assert result is False


# ---------------------------------------------------------------------------
# _apply_successful_refund_side_effects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_successful_refund_side_effects_disables_subscription() -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(id=1, user_id=10, subscription_id=55)
    mocks["subscriptions"].disable = AsyncMock()
    mocks["notifications"].notify_refund_processed = AsyncMock()

    await service._apply_successful_refund_side_effects(payment)

    mocks["subscriptions"].disable.assert_awaited_once_with(
        subscription_id=55, disabled_reason=DisabledReason.REFUNDED, admin_id=None
    )
    mocks["notifications"].notify_refund_processed.assert_awaited_once_with(
        user_id=10, subscription_id=55
    )


@pytest.mark.asyncio
async def test_apply_successful_refund_side_effects_no_subscription_skips_disable() -> (
    None
):
    service, mocks = make_service()
    payment = SimpleNamespace(id=1, user_id=10, subscription_id=None)
    mocks["subscriptions"].disable = AsyncMock()
    mocks["notifications"].notify_refund_processed = AsyncMock()

    await service._apply_successful_refund_side_effects(payment)

    mocks["subscriptions"].disable.assert_not_awaited()
    mocks["notifications"].notify_refund_processed.assert_awaited_once_with(
        user_id=10, subscription_id=None
    )


# ---------------------------------------------------------------------------
# process_refund_result — недостающие not-found ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_refund_result_refund_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["refunds"].get_by_provider_refund_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await service.process_refund_result(
            provider_refund_id="unknown", status=RefundStatus.SUCCEEDED
        )


@pytest.mark.asyncio
async def test_process_refund_result_payment_not_found_raises() -> None:
    service, mocks = make_service()
    refund = SimpleNamespace(
        id=1,
        status=RefundStatus.PENDING,
        completed_at=None,
        payment_id=42,
        amount=1000,
    )
    mocks["refunds"].get_by_provider_refund_id = AsyncMock(return_value=refund)
    mocks["payments"].get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Payment 42 not found"):
        await service.process_refund_result(
            provider_refund_id="yk-1", status=RefundStatus.SUCCEEDED
        )
