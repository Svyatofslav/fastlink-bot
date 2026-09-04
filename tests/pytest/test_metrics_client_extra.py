from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from clients.metrics import MetricsClient, MetricsCredentials


def make_client() -> MetricsClient:
    creds = MetricsCredentials(url="http://example.com/metrics", timeout_seconds=5)
    return MetricsClient(credentials=creds)


@pytest.mark.asyncio
async def test_get_node_metrics_all_retries_fail_returns_degraded(
    monkeypatch,
) -> None:
    client = make_client()
    monkeypatch.setattr(
        client._client,
        "get",
        AsyncMock(
            side_effect=httpx.RequestError(
                "connection refused", request=httpx.Request("GET", "http://example.com")
            )
        ),
    )

    result = await client.get_node_metrics(bearer_token="tok", retries=2)

    assert result.degraded is True
    assert result.cpu_percent == 0.0
    assert result.error_message is not None
    assert "Network error" in result.error_message


@pytest.mark.asyncio
async def test_get_node_metrics_http_error_returns_degraded(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(status_code=503, text="unavailable")
    monkeypatch.setattr(client._client, "get", AsyncMock(return_value=response))

    result = await client.get_node_metrics(bearer_token="tok", retries=1)

    assert result.degraded is True
    assert "status=503" in result.error_message


@pytest.mark.asyncio
async def test_get_node_metrics_invalid_json_returns_degraded(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(status_code=200, content=b"not json")
    monkeypatch.setattr(client._client, "get", AsyncMock(return_value=response))

    result = await client.get_node_metrics(bearer_token="tok", retries=0)

    assert result.degraded is True
    assert "Invalid JSON" in result.error_message


@pytest.mark.asyncio
async def test_get_node_metrics_success_returns_real_values(monkeypatch) -> None:
    client = make_client()
    response = httpx.Response(
        status_code=200,
        json={
            "cpu_percent": 12.5,
            "ram_percent": 55.0,
            "disk_percent": 30.0,
            "uptime_seconds": 999,
        },
    )
    monkeypatch.setattr(client._client, "get", AsyncMock(return_value=response))

    result = await client.get_node_metrics(bearer_token="tok")

    assert result.degraded is False
    assert result.cpu_percent == 12.5
    assert result.uptime_seconds == 999
    assert result.error_message is None


@pytest.mark.asyncio
async def test_aclose_closes_httpx_client() -> None:
    client = make_client()
    client._client.aclose = AsyncMock()

    await client.aclose()

    client._client.aclose.assert_awaited_once()
