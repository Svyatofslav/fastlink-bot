from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from clients.marzban import (
    MarzbanClient,
    MarzbanCredentials,
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
# _parse_user_info
# ---------------------------------------------------------------------------


def test_parse_user_info_full_payload() -> None:
    client = make_client()
    data = {
        "username": "user1",
        "enabled": False,
        "data_limit_bytes": 1000,
        "data_used_bytes": 200,
        "expiry_timestamp": 123456,
        "links": ["https://a", "https://b"],
    }

    info = client._parse_user_info(data)

    assert info.username == "user1"
    assert info.enabled is False
    assert info.data_limit_bytes == 1000
    assert info.data_used_bytes == 200
    assert info.expiry_timestamp == 123456
    assert info.config_links == ["https://a", "https://b"]


def test_parse_user_info_defaults_for_missing_optional_fields() -> None:
    client = make_client()
    data = {"username": "user2"}

    info = client._parse_user_info(data)

    assert info.username == "user2"
    assert info.enabled is True
    assert info.data_limit_bytes == 0
    assert info.data_used_bytes == 0
    assert info.expiry_timestamp is None
    assert info.config_links == []


# ---------------------------------------------------------------------------
# build_subscription_url / get_primary_config_link
# ---------------------------------------------------------------------------


def test_build_subscription_url() -> None:
    client = make_client()

    url = client.build_subscription_url("tok123")

    assert url == "https://fastlinkproject.com/sub/tok123"


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
# create_user / get_user / set_user_traffic / set_user_enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_calls_request_and_parses_response(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=201,
        json={
            "username": "newuser",
            "enabled": True,
            "data_limit_bytes": 500,
            "data_used_bytes": 0,
            "expiry_timestamp": 999,
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
    request_mock.assert_awaited_once_with(
        method="POST",
        path="/users",
        json={
            "username": "newuser",
            "inbound": "inbound-1",
            "data_limit_bytes": 500,
            "expiry_timestamp": 999,
            "enabled": True,
        },
    )


@pytest.mark.asyncio
async def test_get_user_calls_request_and_parses_response(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200,
        json={
            "username": "existing",
            "enabled": True,
            "data_limit_bytes": 100,
            "data_used_bytes": 10,
            "expiry_timestamp": None,
            "links": ["https://l"],
        },
    )
    request_mock = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_request", request_mock)

    result = await client.get_user("existing")

    assert result.username == "existing"
    assert result.config_links == ["https://l"]
    request_mock.assert_awaited_once_with(method="GET", path="/users/existing")


@pytest.mark.asyncio
async def test_set_user_traffic_sends_correct_body(monkeypatch) -> None:
    client = make_client()
    request_mock = AsyncMock(return_value=httpx.Response(status_code=200))
    monkeypatch.setattr(client, "_request", request_mock)

    await client.set_user_traffic("user1", data_used_bytes=12345)

    request_mock.assert_awaited_once_with(
        method="PATCH",
        path="/users/user1/traffic",
        json={"data_used_bytes": 12345},
    )


@pytest.mark.asyncio
async def test_set_user_enabled_sends_correct_body(monkeypatch) -> None:
    client = make_client()
    request_mock = AsyncMock(return_value=httpx.Response(status_code=200))
    monkeypatch.setattr(client, "_request", request_mock)

    await client.set_user_enabled("user1", enabled=False)

    request_mock.assert_awaited_once_with(
        method="PATCH",
        path="/users/user1/status",
        json={"enabled": False},
    )
