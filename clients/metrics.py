from __future__ import annotations

from dataclasses import dataclass

import httpx

from config import get_settings


@dataclass(frozen=True)
class MetricsCredentials:
    """
    Базовые учётные данные для доступа к metrics-agent.

    URL берём из Settings.metrics_url, токен передаём всегда как параметр
    (не храним внутри объекта, чтобы не плодить копии секретов).
    """

    url: str
    timeout_seconds: int


@dataclass(frozen=True)
class NodeMetrics:
    """
    Типизированный ответ от metrics-agent.

    Если degraded == True, остальные поля могут быть нулями/дефолтами,
    а error_message содержит текст ошибки.
    """

    cpu_percent: float
    ram_percent: float
    disk_percent: float
    uptime_seconds: int
    degraded: bool = False
    error_message: str | None = None


class MetricsClientError(Exception):
    """Базовое исключение для ошибок MetricsClient."""


class MetricsClient:
    """
    Async-клиент для работы с metrics-agent по HTTP.

    Делает GET-запрос к metrics_url с Bearer-токеном и возвращает NodeMetrics.
    При недоступности метрик возвращает объект в degraded-режиме.
    """

    def __init__(self, credentials: MetricsCredentials | None = None) -> None:
        settings = get_settings()

        if credentials is None:
            # Таймаут можно взять такой же, как у Marzban, чтобы не плодить конфиг.
            credentials = MetricsCredentials(
                url=settings.metrics_url,
                timeout_seconds=settings.marzban_timeout_seconds,
            )

        self._creds = credentials
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._creds.timeout_seconds),
        )

    async def aclose(self) -> None:
        """
        Закрыть HTTP-клиент (вызывать при остановке приложения/worker).
        """
        await self._client.aclose()

    async def get_node_metrics(
        self,
        *,
        bearer_token: str,
        retries: int = 2,
    ) -> NodeMetrics:
        """
        Получить метрики узла (CPU, RAM, disk, uptime) от metrics-agent.

        bearer_token:
            Bearer-токен, уже расшифрованный (ServerRepo.get_server_secrets)
            или взятый из Settings.metrics_token. Никогда не хранится в полях
            объекта, только используется внутри этого метода.

        retries:
            Количество дополнительных попыток при transient-сбоях сети.
        """
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json",
        }

        last_error: str | None = None

        for attempt in range(retries + 1):
            try:
                resp = await self._client.get(self._creds.url, headers=headers)
            except httpx.RequestError as exc:
                last_error = f"Network error calling metrics: {exc}"
                continue

            if resp.is_client_error or resp.is_server_error:
                # При ошибках HTTP не поднимаем исключение, а переходим к degraded.
                last_error = (
                    f"Metrics HTTP error: status={resp.status_code}, body={resp.text}"
                )
                continue

            try:
                data = resp.json()
            except ValueError as exc:
                last_error = f"Invalid JSON from metrics: {exc}"
                continue

            # Ожидаемый формат JSON от metrics-agent (MVP):
            # {
            #   "cpu_percent": 23.5,
            #   "ram_percent": 68.2,
            #   "disk_percent": 40.1,
            #   "uptime_seconds": 123456
            # }
            cpu = float(data.get("cpu_percent", 0.0))
            ram = float(data.get("ram_percent", 0.0))
            disk = float(data.get("disk_percent", 0.0))
            uptime = int(data.get("uptime_seconds", 0))

            return NodeMetrics(
                cpu_percent=cpu,
                ram_percent=ram,
                disk_percent=disk,
                uptime_seconds=uptime,
                degraded=False,
                error_message=None,
            )

        # Если все попытки провалились, возвращаем degraded-ответ.
        return NodeMetrics(
            cpu_percent=0.0,
            ram_percent=0.0,
            disk_percent=0.0,
            uptime_seconds=0,
            degraded=True,
            error_message=last_error,
        )
