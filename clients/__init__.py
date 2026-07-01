from __future__ import annotations

from clients.marzban import MarzbanClient


def get_marzban_client() -> MarzbanClient:
    """
    Фабрика для MarzbanClient.

    Используется в сервисах/worker’ах, чтобы централизовать создание клиента.
    """
    return MarzbanClient()
