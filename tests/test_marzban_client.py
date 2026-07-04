from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import httpx
import json

from clients.marzban import (
    MarzbanClient,
    MarzbanCredentials,
    MarzbanRequestError,
    MarzbanAuthError,
)


def _make_client(max_retries: int = 2, backoff_base: float = 0.1) -> MarzbanClient:
    # Используем фиксированные креды, чтобы не зависеть от Settings/ENV в этих тестах
    creds = MarzbanCredentials(
        api_base="http://example.com/api",
        username="admin",
        password="password",
        timeout_seconds=5,
    )
    client = MarzbanClient(credentials=creds)

    # Перекрываем _max_retries и _backoff_base напрямую для тестов
    client._max_retries = max_retries
    client._backoff_base = backoff_base
    return client


@pytest.mark.asyncio
async def test_network_error_retries_then_fails(monkeypatch):
    """
    httpx.RequestError → должно быть несколько попыток _request и итоговый MarzbanRequestError.
    """
    client = _make_client(max_retries=2, backoff_base=0.01)

    # Счётчик вызовов request
    call_counter = {"count": 0}

    async def fake_request(*args, **kwargs) -> httpx.Response:
        call_counter["count"] += 1
        raise httpx.RequestError(
            "network down",
            request=httpx.Request("GET", "http://example.com"),
        )

    # Мокаем httpx.AsyncClient.request
    monkeypatch.setattr(client._client, "request", AsyncMock(side_effect=fake_request))

    # Чтобы тест не ждал реальный sleep, мокаем _sleep_with_backoff
    monkeypatch.setattr(client, "_sleep_with_backoff", AsyncMock())

    with pytest.raises(MarzbanRequestError):
        await client._request(method="GET", path="/test")

    # max_retries=2 → 3 попытки (0,1,2)
    assert call_counter["count"] == 3


@pytest.mark.asyncio
async def test_auth_error_no_retry(monkeypatch):
    """
    401/403 → MarzbanAuthError сразу, без повторов.
    """
    client = _make_client(max_retries=3)

    response = httpx.Response(status_code=401, text="unauthorized")
    monkeypatch.setattr(client._client, "request", AsyncMock(return_value=response))

    with pytest.raises(MarzbanAuthError):
        await client._request(method="GET", path="/secure")

    # Должна быть только одна попытка
    client._client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_server_error_retries_then_fails(monkeypatch):
    """
    5xx → должны ретраиться до max_retries, затем MarzbanRequestError.
    """
    client = _make_client(max_retries=2, backoff_base=0.01)

    # Первая и вторая попытки → 500, третья тоже 500
    responses = [
        httpx.Response(status_code=500, text="error-1"),
        httpx.Response(status_code=503, text="error-2"),
        httpx.Response(status_code=500, text="error-3"),
    ]

    async def fake_request(*args, **kwargs) -> httpx.Response:
        return responses.pop(0)

    monkeypatch.setattr(client._client, "request", AsyncMock(side_effect=fake_request))
    monkeypatch.setattr(client, "_sleep_with_backoff", AsyncMock())

    with pytest.raises(MarzbanRequestError):
        await client._request(method="GET", path="/unstable")

    # 3 попытки: 0,1,2
    assert client._client.request.await_count == 3


@pytest.mark.asyncio
async def test_client_error_no_retry(monkeypatch):
    """
    4xx (кроме 401/403) → логическая ошибка, повторять бессмысленно.
    """
    client = _make_client(max_retries=3)

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
    client = _make_client(max_retries=3)

    response = httpx.Response(
        status_code=200,
        content=json.dumps({"ok": True}).encode("utf-8"),
    )
    monkeypatch.setattr(client._client, "request", AsyncMock(return_value=response))

    resp = await client._request(method="GET", path="/ok")

    assert resp.status_code == 200
    client._client.request.assert_awaited_once()
