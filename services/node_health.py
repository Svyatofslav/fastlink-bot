from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from clients import get_metrics_client
from clients.metrics import MetricsClient, NodeMetrics
from config import get_settings
from database.repo.servers import ServerRepo


class NodeHealthService:
    """
    Сервис для получения состояния узла (CPU/RAM/disk/uptime) через metrics-agent.

    Инкапсулирует выбор токена (per-server или общий), retry-логику и degraded-mode.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._servers = ServerRepo(session)
        self._client: MetricsClient = get_metrics_client()
        self._settings = get_settings()

    async def get_server_metrics(self, server_id: int) -> NodeMetrics:
        """
        Вернуть метрики для конкретного сервера.

        Токен берём так:
        - сначала пробуем расшифровать metrics_token через ServerRepo.get_server_secrets;
        - если у сервера токена нет, используем глобальный METRICS_TOKEN из Settings.
        """
        secrets = await self._servers.get_server_secrets(server_id)
        bearer_token: str | None = None

        if secrets is not None and secrets.metrics_token:
            bearer_token = secrets.metrics_token
        else:
            # fallback на общий токен из env, который тоже не хранится в БД.
            bearer_token = self._settings.metrics_token

        # На этом уровне у нас уже есть расшифрованный токен. Не логируем его
        # и не сохраняем в атрибутах, просто передаём в клиент.
        return await self._client.get_node_metrics(bearer_token=bearer_token)
