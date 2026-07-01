from __future__ import annotations

from clients.marzban import MarzbanClient
from clients.metrics import MetricsClient


def get_marzban_client() -> MarzbanClient:
    """
    Фабрика для MarzbanClient.

    Используется в сервисах/worker’ах, чтобы централизовать создание клиента.
    """
    return MarzbanClient()


def get_metrics_client() -> MetricsClient:
    """
    Фабрика для MetricsClient.

    Используется в сервисах/worker’ах, чтобы централизовать создание клиента.
    """
    return MetricsClient()
