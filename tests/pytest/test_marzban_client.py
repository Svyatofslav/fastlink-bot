from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis.aioredis import FakeRedis

from clients.marzban import (
    MarzbanAuthError,
    MarzbanClient,
    MarzbanCredentials,
    MarzbanRequestError,
)


async def _make_client(
    max_retries: int = 2, backoff_base: float = 0.1
) -> MarzbanClient:
    """
    Тестовый MarzbanClient с фейковым Redis вместо реального (иначе тесты
    попытаются достучаться до настоящего хоста 'redis' и упадут с
    DNS/connection error вне docker-сети).

    _fetch_new_token тоже подменяется — иначе force_refresh при 401
    сделает реальный self._client.post(...) на несуществующий /admin/token,
    а мы здесь тестируем только retry/статус-логику _request(), а не
    сам процесс получения токена.
    """
    creds = MarzbanCredentials(
        api_base="http://example.com/api",
        username="admin",
        password="password",
        timeout_seconds=5,
    )
    client = MarzbanClient(credentials=creds, token_cache=FakeRedis())
    client._max_retries = max_retries
    client._backoff_base = backoff_base
    client._fetch_new_token = AsyncMock(return_value="fake-token")  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_network_error_retries_then_fails(monkeypatch):
    """
    httpx.RequestError → должно быть несколько попыток _request и итоговый MarzbanRequestError.
    """
    client = await _make_client(max_retries=2, backoff_base=0.01)

    call_counter = {"count": 0}

    def fake_request(*args, **kwargs) -> httpx.Response:
        call_counter["count"] += 1
        raise httpx.RequestError(
            "network down",
            request=httpx.Request("GET", "http://example.com"),
        )

    monkeypatch.setattr(client._client, "request", AsyncMock(side_effect=fake_request))
    monkeypatch.setattr(client, "_sleep_with_backoff", AsyncMock())

    with pytest.raises(MarzbanRequestError):
        await client._request(method="GET", path="/test")

    assert call_counter["count"] == 3


@pytest.mark.asyncio
async def test_auth_error_no_retry(monkeypatch):
    """
    401/403 дважды подряд → MarzbanAuthError (первая попытка форсирует
    рефреш токена и повторяет запрос, вторая — уже финальная ошибка).
    """
    client = await _make_client(max_retries=3)

    response = httpx.Response(status_code=401, text="unauthorized")
    monkeypatch.setattr(client._client, "request", AsyncMock(return_value=response))

    with pytest.raises(MarzbanAuthError):
        await client._request(method="GET", path="/secure")

    # Два вызова: первый 401 → force_refresh + повтор, второй 401 → raise
    assert client._client.request.await_count == 2


@pytest.mark.asyncio
async def test_server_error_retries_then_fails(monkeypatch):
    """
    5xx → должны ретраиться до max_retries, затем MarzbanRequestError.
    """
    client = await _make_client(max_retries=2, backoff_base=0.01)

    responses = [
        httpx.Response(status_code=500, text="error-1"),
        httpx.Response(status_code=503, text="error-2"),
        httpx.Response(status_code=500, text="error-3"),
    ]

    def fake_request(*args, **kwargs) -> httpx.Response:
        return responses.pop(0)

    monkeypatch.setattr(client._client, "request", AsyncMock(side_effect=fake_request))
    monkeypatch.setattr(client, "_sleep_with_backoff", AsyncMock())

    with pytest.raises(MarzbanRequestError):
        await client._request(method="GET", path="/unstable")

    assert client._client.request.await_count == 3


@pytest.mark.asyncio
async def test_client_error_no_retry(monkeypatch):
    """
    4xx (кроме 401/403) → логическая ошибка, повторять бессмысленно.
    """
    client = await _make_client(max_retries=3)

    response = httpx.Response(status_code=404, text="not found")
    monkeypatch.setattr(client._client, "request", AsyncMock(return_value=response))

    with pytest.raises(MarzbanRequestError):
        await client._request(method="GET", path="/missing")

    client._client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_success_response_no_retry(monkeypatch):
    """
    2xx → успешный ответ без повторов.
    """
    client = await _make_client(max_retries=3)

    response = httpx.Response(
        status_code=200,
        content=json.dumps({"ok": True}).encode("utf-8"),
    )
    monkeypatch.setattr(client._client, "request", AsyncMock(return_value=response))

    resp = await client._request(method="GET", path="/ok")

    assert resp.status_code == 200
    client._client.request.assert_awaited_once()
