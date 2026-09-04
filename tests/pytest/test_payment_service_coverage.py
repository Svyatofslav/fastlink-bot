from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from database.enums import PaymentStatus
from services.payment import PaymentService, YooKassaClientError, get_yookassa_client


class _AsyncCM:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False


def make_service(
    yookassa_client: MagicMock | None = None,
) -> tuple[PaymentService, dict[str, MagicMock]]:
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=_AsyncCM())
    session.flush = AsyncMock()

    mocks = {
        "payments": MagicMock(),
        "notifications": MagicMock(),
        "subscriptions": MagicMock(),
    }
    yookassa_client = yookassa_client or MagicMock()

    with (
        patch("services.payment.PaymentRepo", return_value=mocks["payments"]),
        patch(
            "services.payment.NotificationService", return_value=mocks["notifications"]
        ),
        patch(
            "services.payment.SubscriptionService", return_value=mocks["subscriptions"]
        ),
    ):
        service = PaymentService(
            session, yookassa_client=yookassa_client, bot_username="test_bot"
        )
    mocks["session"] = session
    mocks["yookassa"] = yookassa_client
    return service, mocks


# ---------------------------------------------------------------------------
# get_yookassa_client
# ---------------------------------------------------------------------------


def test_get_yookassa_client_returns_fake_when_feature_disabled() -> None:
    settings = SimpleNamespace(feature_payments_enabled=False)
    with (
        patch("services.payment.get_settings", return_value=settings),
        patch("services.payment.FakeYooKassaClient") as fake_cls,
    ):
        get_yookassa_client()
    fake_cls.assert_called_once()


def test_get_yookassa_client_returns_real_when_feature_enabled() -> None:
    settings = SimpleNamespace(feature_payments_enabled=True)
    with (
        patch("services.payment.get_settings", return_value=settings),
        patch("services.payment.YooKassaClient") as real_cls,
    ):
        get_yookassa_client()
    real_cls.assert_called_once()


# ---------------------------------------------------------------------------
# create_payment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_payment_idempotency_hit_before_insert_returns_existing() -> None:
    service, mocks = make_service()
    existing = SimpleNamespace(id=1)
    mocks["payments"].get_by_idempotence_key = AsyncMock(return_value=existing)

    result = await service.create_payment(
        user_id=1, amount=1000, currency="RUB", idempotency_key="key-1"
    )

    assert result is existing
    mocks["payments"].create.assert_not_called()


@pytest.mark.asyncio
async def test_create_payment_race_detected_returns_existing() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_idempotence_key = AsyncMock(
        side_effect=[None, SimpleNamespace(id=2)]
    )
    mocks["payments"].create = AsyncMock(side_effect=IntegrityError("dup", None, None))

    result = await service.create_payment(
        user_id=1, amount=1000, currency="RUB", idempotency_key="key-race"
    )

    assert result.id == 2


@pytest.mark.asyncio
async def test_create_payment_race_unresolved_reraises() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_idempotence_key = AsyncMock(side_effect=[None, None])
    mocks["payments"].create = AsyncMock(side_effect=IntegrityError("dup", None, None))

    with pytest.raises(IntegrityError):
        await service.create_payment(
            user_id=1, amount=1000, currency="RUB", idempotency_key="key-race-2"
        )


@pytest.mark.asyncio
async def test_create_payment_happy_path_donation_metadata() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_idempotence_key = AsyncMock(return_value=None)
    created_payment = SimpleNamespace(id=10)
    mocks["payments"].create = AsyncMock(return_value=created_payment)
    link = SimpleNamespace(
        provider_payment_id="pid-1", confirmation_url="https://y.example/pay/10"
    )
    mocks["yookassa"].create_payment_link = AsyncMock(return_value=link)
    updated = SimpleNamespace(id=10, confirmation_url="https://y.example/pay/10")
    mocks["payments"].update = AsyncMock(return_value=updated)

    with patch(
        "services.payment.build_yookassa_donation_flat_metadata",
        return_value={"flat": "donation"},
    ) as donation_meta:
        result = await service.create_payment(
            user_id=1,
            amount=1000,
            currency="RUB",
            idempotency_key="key-donation",
            metadata_snapshot={"type": "donation", "user_id": "1"},
        )

    donation_meta.assert_called_once()
    assert result is updated
    mocks["yookassa"].create_payment_link.assert_awaited_once()
    call_kwargs = mocks["yookassa"].create_payment_link.await_args.kwargs
    assert call_kwargs["metadata"] == {"flat": "donation"}
    assert call_kwargs["return_url"] == "https://t.me/test_bot?start=payment_10"


@pytest.mark.asyncio
async def test_create_payment_happy_path_purchase_metadata() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_idempotence_key = AsyncMock(return_value=None)
    created_payment = SimpleNamespace(id=11)
    mocks["payments"].create = AsyncMock(return_value=created_payment)
    link = SimpleNamespace(
        provider_payment_id="pid-2", confirmation_url="https://y.example/pay/11"
    )
    mocks["yookassa"].create_payment_link = AsyncMock(return_value=link)
    updated = SimpleNamespace(id=11, confirmation_url="https://y.example/pay/11")
    mocks["payments"].update = AsyncMock(return_value=updated)

    with patch(
        "services.payment.build_yookassa_flat_metadata",
        return_value={"flat": "purchase"},
    ) as purchase_meta:
        result = await service.create_payment(
            user_id=1,
            amount=1000,
            currency="RUB",
            idempotency_key="key-purchase",
            metadata_snapshot={"type": "purchase", "tariff_id": "1"},
        )

    purchase_meta.assert_called_once()
    assert result is updated


@pytest.mark.asyncio
async def test_create_payment_yookassa_error_is_logged_and_reraised() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_idempotence_key = AsyncMock(return_value=None)
    mocks["payments"].create = AsyncMock(return_value=SimpleNamespace(id=12))
    mocks["yookassa"].create_payment_link = AsyncMock(
        side_effect=YooKassaClientError("boom")
    )

    with pytest.raises(YooKassaClientError):
        await service.create_payment(
            user_id=1, amount=1000, currency="RUB", idempotency_key="key-error"
        )


@pytest.mark.asyncio
async def test_create_payment_missing_confirmation_url_raises_runtime_error() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_idempotence_key = AsyncMock(return_value=None)
    mocks["payments"].create = AsyncMock(return_value=SimpleNamespace(id=13))
    link = SimpleNamespace(provider_payment_id="pid-3", confirmation_url="https://x")
    mocks["yookassa"].create_payment_link = AsyncMock(return_value=link)
    mocks["payments"].update = AsyncMock(
        return_value=SimpleNamespace(id=13, confirmation_url=None)
    )

    with pytest.raises(RuntimeError, match="confirmation_url"):
        await service.create_payment(
            user_id=1, amount=1000, currency="RUB", idempotency_key="key-no-url"
        )


# ---------------------------------------------------------------------------
# attach_provider_payment_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_provider_payment_id_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await service.attach_provider_payment_id(
            payment_id=999, provider_payment_id="pid"
        )


@pytest.mark.asyncio
async def test_attach_provider_payment_id_success() -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(id=1)
    mocks["payments"].get_by_id = AsyncMock(return_value=payment)
    updated = SimpleNamespace(id=1, provider_payment_id="pid")
    mocks["payments"].update = AsyncMock(return_value=updated)

    result = await service.attach_provider_payment_id(
        payment_id=1, provider_payment_id="pid"
    )

    assert result is updated
    mocks["payments"].update.assert_awaited_once_with(
        payment, provider_payment_id="pid"
    )


# ---------------------------------------------------------------------------
# process_successful_payment — недостающие ветки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_successful_payment_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await service.process_successful_payment(provider_payment_id="pid")


@pytest.mark.asyncio
async def test_process_successful_payment_already_refunded_returns_early() -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(
        id=1, status=PaymentStatus.REFUNDED_PARTIALLY, subscription_id=None
    )
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=payment)

    result = await service.process_successful_payment(provider_payment_id="pid")

    assert result is payment
    mocks["payments"].set_status.assert_not_called()


@pytest.mark.asyncio
async def test_process_successful_payment_links_subscription_id_when_missing() -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(
        id=1, status=PaymentStatus.PENDING, subscription_id=None, user_id=5
    )
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=payment)
    after_set_status = SimpleNamespace(
        id=1, status=PaymentStatus.SUCCEEDED, subscription_id=None, user_id=5
    )
    mocks["payments"].set_status = AsyncMock(return_value=after_set_status)
    after_update = SimpleNamespace(
        id=1,
        status=PaymentStatus.SUCCEEDED,
        subscription_id=77,
        user_id=5,
        metadata_snapshot=None,
    )
    mocks["payments"].update = AsyncMock(return_value=after_update)

    result = await service.process_successful_payment(
        provider_payment_id="pid", subscription_id=77
    )

    mocks["payments"].update.assert_awaited_once_with(
        after_set_status, subscription_id=77
    )
    assert result.subscription_id == 77


@pytest.mark.asyncio
async def test_process_successful_payment_creates_new_subscription() -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(
        id=1, status=PaymentStatus.PENDING, subscription_id=None, user_id=5
    )
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=payment)
    after_set_status = SimpleNamespace(
        id=1, status=PaymentStatus.SUCCEEDED, subscription_id=None, user_id=5
    )
    mocks["payments"].set_status = AsyncMock(return_value=after_set_status)
    new_subscription = SimpleNamespace(id=99)
    mocks["subscriptions"].create_for_payment = AsyncMock(return_value=new_subscription)
    after_update = SimpleNamespace(
        id=1,
        status=PaymentStatus.SUCCEEDED,
        subscription_id=99,
        user_id=5,
        metadata_snapshot=None,
    )
    mocks["payments"].update = AsyncMock(return_value=after_update)

    params = SimpleNamespace(
        tariff_id=1,
        server_id=2,
        marzban_username="user1",
        starts_at=None,
        expires_at=None,
    )

    result = await service.process_successful_payment(
        provider_payment_id="pid", new_subscription_params=params
    )

    mocks["subscriptions"].create_for_payment.assert_awaited_once_with(
        user_id=5,
        tariff_id=1,
        server_id=2,
        marzban_username="user1",
        starts_at=None,
        expires_at=None,
    )
    mocks["payments"].update.assert_awaited_once_with(
        after_set_status, subscription_id=99
    )
    assert result.subscription_id == 99


# ---------------------------------------------------------------------------
# process_canceled_payment — метод вообще не был протестирован на уровне сервиса
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_canceled_payment_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await service.process_canceled_payment(provider_payment_id="pid")


@pytest.mark.asyncio
async def test_process_canceled_payment_already_canceled_is_noop() -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(id=1, status=PaymentStatus.CANCELED)
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=payment)

    result = await service.process_canceled_payment(provider_payment_id="pid")

    assert result is payment
    mocks["payments"].set_status.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        PaymentStatus.SUCCEEDED,
        PaymentStatus.REFUNDED_PARTIALLY,
        PaymentStatus.REFUNDED_FULLY,
    ],
)
async def test_process_canceled_payment_after_succeeded_does_not_rollback(
    status: PaymentStatus,
) -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(id=1, status=status)
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=payment)

    result = await service.process_canceled_payment(provider_payment_id="pid")

    assert result is payment
    mocks["payments"].set_status.assert_not_called()


@pytest.mark.asyncio
async def test_process_canceled_payment_happy_path_sets_canceled() -> None:
    service, mocks = make_service()
    payment = SimpleNamespace(id=1, status=PaymentStatus.PENDING)
    mocks["payments"].get_by_provider_payment_id = AsyncMock(return_value=payment)
    canceled = SimpleNamespace(id=1, status=PaymentStatus.CANCELED)
    mocks["payments"].set_status = AsyncMock(return_value=canceled)

    result = await service.process_canceled_payment(
        provider_payment_id="pid", metadata_snapshot={"reason": "user_request"}
    )

    assert result is canceled
    mocks["payments"].set_status.assert_awaited_once_with(
        payment,
        status=PaymentStatus.CANCELED,
        metadata_snapshot={"reason": "user_request"},
        refundable=False,
    )


# ---------------------------------------------------------------------------
# cancel_pending_payment — недостающая not-found ветка
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_pending_payment_not_found_raises() -> None:
    service, mocks = make_service()
    mocks["payments"].get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        await service.cancel_pending_payment(payment_id=999)
