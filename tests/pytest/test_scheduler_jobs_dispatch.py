from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database.enums import RefundStatus
from database.repo.webhook_events import WebhookEventsRepo
from scheduler.jobs import (
    _build_new_subscription_params,
    _handle_payment_canceled,
    _handle_refund_event,
    handle_single_event,
)
from services.payment import NewSubscriptionParams


def make_event(
    *,
    event_id: int = 1,
    provider: str = "yookassa",
    event_type: str = "payment.succeeded",
    payload: dict | None = None,
    external_id: str = "ext-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id,
        provider=provider,
        event_type=event_type,
        payload=payload or {},
        external_id=external_id,
    )


def make_repo() -> MagicMock:
    repo = MagicMock(spec=WebhookEventsRepo)
    repo.session = MagicMock()
    return repo


# ---------------------------------------------------------------------------
# handle_single_event — диспетчеризация по event.provider / event.event_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_single_event_unknown_provider_skips_all_handlers() -> None:
    repo = make_repo()
    event = make_event(provider="stripe", event_type="payment.succeeded")

    with (
        patch("scheduler.jobs._handle_payment_succeeded", new=AsyncMock()) as succeeded,
        patch("scheduler.jobs._handle_payment_canceled", new=AsyncMock()) as canceled,
        patch("scheduler.jobs._handle_refund_event", new=AsyncMock()) as refund,
    ):
        await handle_single_event(repo, event, bot=None)

    succeeded.assert_not_awaited()
    canceled.assert_not_awaited()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_single_event_dispatches_payment_succeeded() -> None:
    repo = make_repo()
    event = make_event(event_type="payment.succeeded", payload={"object": {"id": "x"}})
    bot = MagicMock()

    with patch(
        "scheduler.jobs._handle_payment_succeeded", new=AsyncMock()
    ) as succeeded:
        await handle_single_event(repo, event, bot=bot)

    succeeded.assert_awaited_once_with(repo.session, event, event.payload, bot=bot)


@pytest.mark.asyncio
async def test_handle_single_event_dispatches_payment_canceled() -> None:
    repo = make_repo()
    event = make_event(event_type="payment.canceled", payload={"object": {"id": "x"}})

    with patch("scheduler.jobs._handle_payment_canceled", new=AsyncMock()) as canceled:
        await handle_single_event(repo, event, bot=None)

    canceled.assert_awaited_once_with(repo.session, event, event.payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "expected_status"),
    [
        ("refund.succeeded", RefundStatus.SUCCEEDED),
        ("refund.canceled", RefundStatus.CANCELED),
        ("refund.failed", RefundStatus.FAILED),
    ],
)
async def test_handle_single_event_dispatches_refund_events(
    event_type: str, expected_status: RefundStatus
) -> None:
    repo = make_repo()
    event = make_event(event_type=event_type, payload={"object": {"id": "r-1"}})

    with patch("scheduler.jobs._handle_refund_event", new=AsyncMock()) as refund:
        await handle_single_event(repo, event, bot=None)

    refund.assert_awaited_once_with(repo.session, event, event.payload, expected_status)


@pytest.mark.asyncio
async def test_handle_single_event_unhandled_type_does_not_raise() -> None:
    repo = make_repo()
    event = make_event(event_type="payment.waiting_for_capture", payload={})

    with (
        patch("scheduler.jobs._handle_payment_succeeded", new=AsyncMock()) as succeeded,
        patch("scheduler.jobs._handle_payment_canceled", new=AsyncMock()) as canceled,
        patch("scheduler.jobs._handle_refund_event", new=AsyncMock()) as refund,
    ):
        await handle_single_event(repo, event, bot=None)

    succeeded.assert_not_awaited()
    canceled.assert_not_awaited()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_single_event_non_dict_payload_treated_as_empty() -> None:
    """event.payload может быть, например, None/строкой из-за malformed данных —
    handle_single_event должен подставить {} и всё равно дойти до диспетчеризации,
    а не упасть на попытке вызвать .get на не-dict."""
    repo = make_repo()
    event = make_event(event_type="payment.canceled", payload="not-a-dict")

    with patch("scheduler.jobs._handle_payment_canceled", new=AsyncMock()) as canceled:
        await handle_single_event(repo, event, bot=None)

    canceled.assert_awaited_once_with(repo.session, event, {})


# ---------------------------------------------------------------------------
# _handle_payment_canceled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_payment_canceled_calls_payment_service() -> None:
    event = make_event(event_type="payment.canceled")
    payload = {
        "object": {
            "id": "yk-canceled-1",
            "amount": {"value": "100.00", "currency": "RUB"},
            "paid": False,
            "description": "test",
            "metadata": {},
        }
    }
    session = MagicMock()
    payment_service = MagicMock()
    payment_service.process_canceled_payment = AsyncMock()

    with patch("scheduler.jobs.PaymentService", return_value=payment_service):
        await _handle_payment_canceled(session, event, payload)

    payment_service.process_canceled_payment.assert_awaited_once()
    call_kwargs = payment_service.process_canceled_payment.await_args.kwargs
    assert call_kwargs["provider_payment_id"] == "yk-canceled-1"
    assert call_kwargs["metadata_snapshot"]["amount_value"] == "100.00"
    assert call_kwargs["metadata_snapshot"]["amount_currency"] == "RUB"


@pytest.mark.asyncio
async def test_handle_payment_canceled_missing_object_raises() -> None:
    event = make_event(event_type="payment.canceled")
    session = MagicMock()

    with pytest.raises(ValueError, match="missing 'object'"):
        await _handle_payment_canceled(session, event, payload={})


@pytest.mark.asyncio
async def test_handle_payment_canceled_missing_id_raises() -> None:
    event = make_event(event_type="payment.canceled")
    session = MagicMock()

    with pytest.raises(ValueError, match="missing 'id'"):
        await _handle_payment_canceled(session, event, payload={"object": {}})


# ---------------------------------------------------------------------------
# _handle_refund_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [RefundStatus.SUCCEEDED, RefundStatus.CANCELED, RefundStatus.FAILED],
)
async def test_handle_refund_event_calls_refund_service(status: RefundStatus) -> None:
    event = make_event(event_type=f"refund.{status.value.lower()}")
    payload = {"object": {"id": "yk-refund-1", "status": status.value}}
    session = MagicMock()
    refund_service = MagicMock()
    refund_service.process_refund_result = AsyncMock()

    with patch("scheduler.jobs.RefundService", return_value=refund_service):
        await _handle_refund_event(session, event, payload, status)

    refund_service.process_refund_result.assert_awaited_once_with(
        provider_refund_id="yk-refund-1",
        status=status,
        raw_payload=payload["object"],
    )


@pytest.mark.asyncio
async def test_handle_refund_event_missing_object_raises() -> None:
    event = make_event(event_type="refund.succeeded")
    session = MagicMock()

    with pytest.raises(ValueError, match="missing 'object'"):
        await _handle_refund_event(
            session, event, payload={}, status=RefundStatus.SUCCEEDED
        )


@pytest.mark.asyncio
async def test_handle_refund_event_missing_id_raises() -> None:
    event = make_event(event_type="refund.succeeded")
    session = MagicMock()

    with pytest.raises(ValueError, match="missing 'id'"):
        await _handle_refund_event(
            session, event, payload={"object": {}}, status=RefundStatus.SUCCEEDED
        )


# ---------------------------------------------------------------------------
# _build_new_subscription_params
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_key",
    ["tariff_id", "server_id", "marzban_username", "expires_at"],
)
def test_build_new_subscription_params_missing_key_returns_none(
    missing_key: str,
) -> None:
    metadata = {
        "tariff_id": "1",
        "server_id": "2",
        "marzban_username": "user1",
        "expires_at": "2026-09-01T00:00:00+00:00",
    }
    del metadata[missing_key]

    assert _build_new_subscription_params(metadata) is None


def test_build_new_subscription_params_all_keys_present_builds_model() -> None:
    metadata = {
        "tariff_id": "1",
        "server_id": "2",
        "marzban_username": "user1",
        "expires_at": "2026-09-01T00:00:00+00:00",
    }

    result = _build_new_subscription_params(metadata)

    assert isinstance(result, NewSubscriptionParams)
