from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from clients.metrics import MetricsClient, NodeMetrics


def _make_metrics_client(max_retries: int = 2) -> MetricsClient:
    # В текущей реализации max_retries скорее всего задаётся аргументом метода,
    # поэтому здесь просто создаём клиент как есть.
    return MetricsClient()


@pytest.mark.asyncio
async def test_metrics_degraded_on_network_error(monkeypatch):
    """
    При сетевой ошибке после всех попыток возвращается NodeMetrics(degraded=True).
    """
    client = _make_metrics_client()

    def fake_get(*args, **kwargs) -> httpx.Response:
        raise httpx.RequestError(
            "network down", request=httpx.Request("GET", "http://example.com/metrics")
        )

    monkeypatch.setattr(client._client, "get", AsyncMock(side_effect=fake_get))

    metrics = await client.get_node_metrics(bearer_token="test", retries=2)

    assert isinstance(metrics, NodeMetrics)
    assert metrics.degraded is True
    assert "network down" in (metrics.error_message or "")


@pytest.mark.asyncio
async def test_metrics_degraded_on_server_error(monkeypatch):
    """
    При 5xx после retries возвращается degraded=True.
    """
    client = _make_metrics_client()

    responses = [
        httpx.Response(status_code=500, text="error-1"),
        httpx.Response(status_code=503, text="error-2"),
        httpx.Response(status_code=500, text="error-3"),
    ]

    def fake_get(*args, **kwargs) -> httpx.Response:
        return responses.pop(0)

    monkeypatch.setattr(client._client, "get", AsyncMock(side_effect=fake_get))

    metrics = await client.get_node_metrics(bearer_token="test", retries=2)

    assert metrics.degraded is True
    assert metrics.error_message is not None


@pytest.mark.asyncio
async def test_metrics_success_not_degraded(monkeypatch):
    """
    При валидном ответе degraded=False и поля заполнены.
    """
    client = _make_metrics_client()

    response = httpx.Response(
        status_code=200,
        content=json.dumps(
            {
                "cpu_percent": 10.0,
                "ram_percent": 20.0,
                "disk_percent": 30.0,
                "uptime_seconds": 5,
            }
        ).encode("utf-8"),
    )

    monkeypatch.setattr(client._client, "get", AsyncMock(return_value=response))

    metrics = await client.get_node_metrics(bearer_token="test", retries=0)

    assert metrics.degraded is False
    assert metrics.cpu_percent == 10.0
    assert metrics.ram_percent == 20.0
    assert metrics.disk_percent == 30.0
    assert metrics.uptime_seconds == 5
