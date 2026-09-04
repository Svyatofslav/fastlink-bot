from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from clients.yookassa import (
    FakeYooKassaClient,
    YooKassaClient,
    YooKassaClientError,
    YooKassaCredentials,
    YooKassaPaymentLink,
)


def make_client() -> YooKassaClient:
    creds = YooKassaCredentials(shop_id="shop-1", secret_key="secret-1")
    return YooKassaClient(credentials=creds)


# ---------------------------------------------------------------------------
# __init__ / aclose
# ---------------------------------------------------------------------------


def test_init_with_explicit_credentials() -> None:
    creds = YooKassaCredentials(shop_id="s", secret_key="k")
    client = YooKassaClient(credentials=creds)

    assert client.creds is creds


def test_init_without_credentials_uses_settings() -> None:
    fake_settings = SimpleNamespace(
        yookassa_shop_id="shop-from-settings", yookassa_secret_key="key-from-settings"
    )

    with patch("clients.yookassa.get_settings", return_value=fake_settings):
        client = YooKassaClient()

    assert client.creds.shop_id == "shop-from-settings"
    assert client.creds.secret_key == "key-from-settings"


@pytest.mark.asyncio
async def test_aclose_closes_httpx_client() -> None:
    client = make_client()
    client.client.aclose = AsyncMock()

    await client.aclose()

    client.client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# create_payment_link — real YooKassaClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_payment_link_success(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200,
        json={
            "id": "yk-payment-1",
            "confirmation": {"confirmation_url": "https://yookassa.example/pay/1"},
        },
    )
    post_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client.client, "post", post_mock)

    result = await client.create_payment_link(
        amount=10000,
        currency="RUB",
        description="test payment",
        idempotency_key="idem-1",
        return_url="https://t.me/bot?start=payment_1",
        metadata={"user_id": "1"},
    )

    assert isinstance(result, YooKassaPaymentLink)
    assert result.provider_payment_id == "yk-payment-1"
    assert result.confirmation_url == "https://yookassa.example/pay/1"

    call_kwargs = post_mock.await_args.kwargs
    assert call_kwargs["headers"] == {"Idempotence-Key": "idem-1"}
    assert call_kwargs["auth"] == ("shop-1", "secret-1")
    assert call_kwargs["json"]["amount"] == {"value": "100.00", "currency": "RUB"}
    assert call_kwargs["json"]["metadata"] == {"user_id": "1"}


@pytest.mark.asyncio
async def test_create_payment_link_no_metadata_defaults_to_empty_dict(
    monkeypatch,
) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200,
        json={
            "id": "yk-payment-2",
            "confirmation": {"confirmation_url": "https://yookassa.example/pay/2"},
        },
    )
    post_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client.client, "post", post_mock)

    await client.create_payment_link(
        amount=5000,
        currency="RUB",
        description="test",
        idempotency_key="idem-2",
        return_url="https://t.me/bot?start=payment_2",
    )

    call_kwargs = post_mock.await_args.kwargs
    assert call_kwargs["json"]["metadata"] == {}


@pytest.mark.asyncio
async def test_create_payment_link_network_error_raises_client_error(
    monkeypatch,
) -> None:
    client = make_client()
    post_mock = AsyncMock(
        side_effect=httpx.RequestError(
            "network down", request=httpx.Request("POST", "https://yookassa.example")
        )
    )
    monkeypatch.setattr(client.client, "post", post_mock)

    with pytest.raises(YooKassaClientError, match="Network error"):
        await client.create_payment_link(
            amount=1000,
            currency="RUB",
            description="test",
            idempotency_key="idem-3",
            return_url="https://t.me/bot",
        )


@pytest.mark.asyncio
async def test_create_payment_link_error_status_raises_client_error(
    monkeypatch,
) -> None:
    client = make_client()
    response = httpx.Response(status_code=400, text="bad request")
    post_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client.client, "post", post_mock)

    with pytest.raises(YooKassaClientError, match="status=400"):
        await client.create_payment_link(
            amount=1000,
            currency="RUB",
            description="test",
            idempotency_key="idem-4",
            return_url="https://t.me/bot",
        )


@pytest.mark.asyncio
async def test_create_payment_link_malformed_response_missing_id_raises(
    monkeypatch,
) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200,
        json={"confirmation": {"confirmation_url": "https://yookassa.example/pay/x"}},
    )
    post_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client.client, "post", post_mock)

    with pytest.raises(YooKassaClientError, match="Malformed"):
        await client.create_payment_link(
            amount=1000,
            currency="RUB",
            description="test",
            idempotency_key="idem-5",
            return_url="https://t.me/bot",
        )


@pytest.mark.asyncio
async def test_create_payment_link_malformed_response_missing_confirmation_url_raises(
    monkeypatch,
) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200,
        json={"id": "yk-payment-6", "confirmation": {}},
    )
    post_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client.client, "post", post_mock)

    with pytest.raises(YooKassaClientError, match="Malformed"):
        await client.create_payment_link(
            amount=1000,
            currency="RUB",
            description="test",
            idempotency_key="idem-6",
            return_url="https://t.me/bot",
        )


# ---------------------------------------------------------------------------
# FakeYooKassaClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_client_aclose_is_noop() -> None:
    client = FakeYooKassaClient()

    result = await client.aclose()

    assert result is None


@pytest.mark.asyncio
async def test_fake_client_create_payment_link_returns_placeholder() -> None:
    client = FakeYooKassaClient()

    result = await client.create_payment_link(
        amount=1000,
        currency="RUB",
        description="test",
        idempotency_key="idem-fake",
        return_url="https://t.me/bot",
        metadata={"foo": "bar"},
    )

    assert isinstance(result, YooKassaPaymentLink)
    assert result.provider_payment_id.startswith("fake_")
    assert result.confirmation_url == "https://example.com/PLACEHOLDER"
