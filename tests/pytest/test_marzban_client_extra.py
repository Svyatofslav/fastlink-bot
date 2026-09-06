from __future__ import annotations

import asyncio
import random
from unittest.mock import AsyncMock

import httpx
import pytest

from clients.marzban import (
    MarzbanAuthError,
    MarzbanClient,
    MarzbanCredentials,
    MarzbanRequestError,
    MarzbanUserCreatePayload,
    MarzbanUserInfo,
)


def make_client() -> MarzbanClient:
    creds = MarzbanCredentials(
        api_base="http://example.com/api",
        username="admin",
        password="password",
        timeout_seconds=5,
    )
    return MarzbanClient(credentials=creds)


# ---------------------------------------------------------------------------
# __init__ / aclose
# ---------------------------------------------------------------------------


def test_init_with_explicit_credentials_uses_them() -> None:
    creds = MarzbanCredentials(
        api_base="http://custom.example/api",
        username="u",
        password="p",
        timeout_seconds=7,
    )
    client = MarzbanClient(credentials=creds)

    assert client._creds is creds


@pytest.mark.asyncio
async def test_aclose_closes_httpx_client() -> None:
    client = make_client()
    client._client.aclose = AsyncMock()

    await client.aclose()

    client._client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# _parse_user_info — реальные ключи ответа Marzban (UserResponse)
# ---------------------------------------------------------------------------


def test_parse_user_info_full_payload() -> None:
    client = make_client()
    data = {
        "username": "user1",
        "status": "disabled",
        "data_limit": 1000,
        "used_traffic": 200,
        "expire": 123456,
        "subscription_url": "https://example.com/sub/user1",
        "links": ["https://a", "https://b"],
    }

    info = client._parse_user_info(data)

    assert info.username == "user1"
    assert info.enabled is False
    assert info.data_limit_bytes == 1000
    assert info.data_used_bytes == 200
    assert info.expiry_timestamp == 123456
    assert info.subscription_url == "https://example.com/sub/user1"
    assert info.config_links == ["https://a", "https://b"]


def test_parse_user_info_defaults_for_missing_optional_fields() -> None:
    """
    Без ключа "status" в ответе enabled — False (а не True, как было бы
    "по умолчанию активен"): Marzban явно должен прислать status="active",
    иначе считаем, что пользователь неактивен.
    """
    client = make_client()
    data = {"username": "user2"}

    info = client._parse_user_info(data)

    assert info.username == "user2"
    assert info.enabled is False
    assert info.data_limit_bytes == 0
    assert info.data_used_bytes == 0
    assert info.expiry_timestamp is None
    assert info.subscription_url == ""
    assert info.config_links == []


# ---------------------------------------------------------------------------
# get_primary_config_link
# ---------------------------------------------------------------------------


def test_get_primary_config_link_with_links() -> None:
    client = make_client()
    info = MarzbanUserInfo(
        username="u",
        enabled=True,
        data_limit_bytes=0,
        data_used_bytes=0,
        expiry_timestamp=None,
        config_links=["https://first", "https://second"],
    )

    assert client.get_primary_config_link(info) == "https://first"


def test_get_primary_config_link_no_links_returns_none() -> None:
    client = make_client()
    info = MarzbanUserInfo(
        username="u",
        enabled=True,
        data_limit_bytes=0,
        data_used_bytes=0,
        expiry_timestamp=None,
        config_links=[],
    )

    assert client.get_primary_config_link(info) is None


# ---------------------------------------------------------------------------
# create_user / get_user / update_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_calls_request_and_parses_response(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=201,
        json={
            "username": "newuser",
            "status": "active",
            "data_limit": 500,
            "used_traffic": 0,
            "expire": 999,
            "subscription_url": "https://example.com/sub/newuser",
            "links": [],
        },
    )
    request_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_request", request_mock)

    payload = MarzbanUserCreatePayload(
        username="newuser",
        inbound_tag="inbound-1",
        data_limit_bytes=500,
        expiry_timestamp=999,
    )

    result = await client.create_user(payload)

    assert result.username == "newuser"
    assert result.subscription_url == "https://example.com/sub/newuser"
    request_mock.assert_awaited_once_with(
        method="POST",
        path="user",
        json={
            "username": "newuser",
            "proxies": {"vless": {}},
            "inbounds": {"vless": ["inbound-1"]},
            "data_limit": 500,
            "expire": 999,
            "status": "active",
        },
    )


@pytest.mark.asyncio
async def test_get_user_calls_request_and_parses_response(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200,
        json={
            "username": "existing",
            "status": "active",
            "data_limit": 100,
            "used_traffic": 10,
            "expire": None,
            "links": ["https://l"],
        },
    )
    request_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_request", request_mock)

    result = await client.get_user("existing")

    assert result.username == "existing"
    assert result.config_links == ["https://l"]
    request_mock.assert_awaited_once_with(method="GET", path="user/existing")


@pytest.mark.asyncio
async def test_update_user_enabled_sends_correct_body(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200, json={"username": "user1", "status": "disabled"}
    )
    request_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_request", request_mock)

    await client.update_user("user1", enabled=False)

    request_mock.assert_awaited_once_with(
        method="PUT",
        path="user/user1",
        json={"status": "disabled"},
    )


@pytest.mark.asyncio
async def test_update_user_sends_only_provided_fields(monkeypatch) -> None:
    """Партиальный PUT: если передан только data_limit_bytes, в теле — только data_limit."""
    client = make_client()
    response = httpx.Response(
        status_code=200, json={"username": "user1", "status": "active"}
    )
    request_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_request", request_mock)

    await client.update_user("user1", data_limit_bytes=2000)

    request_mock.assert_awaited_once_with(
        method="PUT",
        path="user/user1",
        json={"data_limit": 2000},
    )


@pytest.mark.asyncio
async def test_update_user_with_no_fields_sends_empty_body(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200, json={"username": "user1", "status": "active"}
    )
    request_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_request", request_mock)

    await client.update_user("user1")

    request_mock.assert_awaited_once_with(method="PUT", path="user/user1", json={})


# ---------------------------------------------------------------------------
# _fetch_new_token — ни разу не вызывалась напрямую в остальных тестах
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_new_token_success(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(status_code=200, json={"access_token": "tok-abc"})
    monkeypatch.setattr(client._client, "post", AsyncMock(return_value=response))

    token = await client._fetch_new_token()

    assert token == "tok-abc"


@pytest.mark.asyncio
async def test_fetch_new_token_network_error_raises(monkeypatch) -> None:
    client = make_client()

    async def fake_post(*args, **kwargs):
        raise httpx.RequestError(
            "network down", request=httpx.Request("POST", "http://example.com")
        )

    monkeypatch.setattr(client._client, "post", AsyncMock(side_effect=fake_post))

    with pytest.raises(MarzbanRequestError, match="Network error"):
        await client._fetch_new_token()


@pytest.mark.asyncio
async def test_fetch_new_token_auth_error_raises(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(status_code=401, text="unauthorized")
    monkeypatch.setattr(client._client, "post", AsyncMock(return_value=response))

    with pytest.raises(MarzbanAuthError):
        await client._fetch_new_token()


@pytest.mark.asyncio
async def test_fetch_new_token_server_error_raises(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(status_code=500, text="internal error")
    monkeypatch.setattr(client._client, "post", AsyncMock(return_value=response))

    with pytest.raises(MarzbanRequestError, match="Marzban token request failed"):
        await client._fetch_new_token()


@pytest.mark.asyncio
async def test_fetch_new_token_malformed_response_raises(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(status_code=200, json={"unexpected": "shape"})
    monkeypatch.setattr(client._client, "post", AsyncMock(return_value=response))

    with pytest.raises(MarzbanRequestError, match="Malformed Marzban token response"):
        await client._fetch_new_token()


# ---------------------------------------------------------------------------
# _sleep_with_backoff — везде подменялась на AsyncMock, реальное тело не тестировалось
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sleep_with_backoff_computes_exponential_delay_with_jitter(
    monkeypatch,
) -> None:
    client = make_client()
    client._backoff_base = 0.5

    monkeypatch.setattr(random, "uniform", lambda a, b: 0.1)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_mock)

    await client._sleep_with_backoff(attempt=2)

    # base_delay = backoff_base * 2**attempt = 0.5 * 4 = 2.0; + jitter 0.1 = 2.1
    sleep_mock.assert_awaited_once_with(2.1)


# ---------------------------------------------------------------------------
# aclose — ветка с внешним (не владеемым) token_cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_does_not_close_externally_provided_token_cache() -> None:
    """
    Если token_cache передан снаружи (owns_token_cache=False), aclose()
    не должен его закрывать — жизненным циклом внешнего Redis-соединения
    управляет вызывающий код, а не MarzbanClient.
    """
    creds = MarzbanCredentials(
        api_base="http://example.com/api",
        username="admin",
        password="password",
        timeout_seconds=5,
    )
    external_token_cache = AsyncMock()
    client = MarzbanClient(credentials=creds, token_cache=external_token_cache)
    client._client.aclose = AsyncMock()

    await client.aclose()

    client._client.aclose.assert_awaited_once()
    external_token_cache.aclose.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_user — недостающий кейс с expiry_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_sends_expiry_timestamp(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200, json={"username": "user1", "status": "active"}
    )
    request_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_request", request_mock)

    await client.update_user("user1", expiry_timestamp=1893456000)

    request_mock.assert_awaited_once_with(
        method="PUT",
        path="user/user1",
        json={"expire": 1893456000},
    )


# ---------------------------------------------------------------------------
# _request — защитная ветка на случай некорректной конфигурации
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_raises_generic_error_when_max_retries_negative() -> None:
    """
    Если max_retries отрицательный (некорректная конфигурация — в норме
    Settings это запрещает через ge=0, но код должен быть устойчив и
    к прямой порче атрибута), цикл retry ни разу не выполнится, и
    last_error останется None. Код обязан поднять общее
    MarzbanRequestError, а не тихо вернуть None/сломаться непонятно как.
    """
    client = make_client()
    client._max_retries = -1

    with pytest.raises(
        MarzbanRequestError, match="Marzban request failed without specific error"
    ):
        await client._request(method="GET", path="/anything")
