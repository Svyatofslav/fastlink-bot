from __future__ import annotations

from functools import lru_cache

from clients.marzban import MarzbanClient
from clients.metrics import MetricsClient


@lru_cache
def get_marzban_client() -> MarzbanClient:
    """Единый переиспользуемый MarzbanClient. Кешируется на весь процесс."""
    return MarzbanClient()


@lru_cache
def get_metrics_client() -> MetricsClient:
    """Единый переиспользуемый MetricsClient. Кешируется на весь процесс."""
    return MetricsClient()
