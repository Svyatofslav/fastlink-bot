from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

import httpx
import structlog

from config import get_settings


@dataclass(frozen=True)
class MarzbanCredentials:
    """
    Базовые учётные данные для доступа к Marzban API.

    По умолчанию используем admin-логин/пароль из Settings.
    """

    api_base: str
    username: str
    password: str
    timeout_seconds: int


class MarzbanClientError(Exception):
    """Базовое исключение для ошибок MarzbanClient."""


class MarzbanAuthError(MarzbanClientError):
    """Ошибка аутентификации/авторизации при запросе к Marzban."""


class MarzbanRequestError(MarzbanClientError):
    """Ошибка сетевого запроса или некорректного ответа."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        # None для сетевых ошибок (httpx.RequestError), где статуса ответа
        # просто нет. Заполнен для всех случаев, когда Marzban реально
        # ответил HTTP-кодом (4xx/5xx) — используется вызывающим кодом
        # для точечной обработки конкретных статусов (например, 409
        # "user already exists" при создании подписки), без парсинга
        # текста сообщения по подстрокам.
        self.status_code = status_code


@dataclass(frozen=True)
class MarzbanUserCreatePayload:
    """
    DTO для создания пользователя в Marzban.

    Привязан к Subscription.marzban_username и Server.inbound_tag.
    """

    username: str
    inbound_tag: str
    data_limit_bytes: int
    expiry_timestamp: int  # UNIX timestamp в секундах
    enabled: bool = True


@dataclass(frozen=True)
class MarzbanUserInfo:
    """
    DTO для информации о пользователе в Marzban.

    Используется в сервисах FastLink, чтобы не таскать сырые dict.
    """

    username: str
    enabled: bool
    data_limit_bytes: int
    data_used_bytes: int
    expiry_timestamp: int | None
    config_links: list[str] = field(default_factory=list)


class MarzbanClient:
    """
    Async-клиент для работы с Marzban API.

    Использует httpx.AsyncClient и admin-логин/пароль из Settings.
    Конкретная нода определяется через inbound_tag/маршрутизацию на стороне Marzban.
    Реализует ограниченный retry для транзиентных ошибок.
    """

    def __init__(self, credentials: MarzbanCredentials | None = None) -> None:
        settings = get_settings()

        if credentials is None:
            credentials = MarzbanCredentials(
                api_base=settings.marzban_api_base,
                username=settings.marzban_username,
                password=settings.marzban_password,
                timeout_seconds=settings.marzban_timeout_seconds,
            )

        self._creds = credentials
        self._max_retries = settings.marzban_max_retries
        self._backoff_base = settings.marzban_backoff_base_seconds
        self._logger = structlog.get_logger(__name__)

        self._client = httpx.AsyncClient(
            base_url=self._creds.api_base.rstrip("/"),
            timeout=httpx.Timeout(self._creds.timeout_seconds),
        )

    async def aclose(self) -> None:
        """
        Закрыть HTTP-клиент (вызывать при остановке приложения/worker).
        """
        await self._client.aclose()

    async def _sleep_with_backoff(self, attempt: int) -> None:
        """
        Экспоненциальный backoff с небольшим jitter, чтобы не долбить Marzban синхронно.
        attempt: 0, 1, 2, ...
        """
        base_delay = self._backoff_base * (2**attempt)
        jitter = random.uniform(0, self._backoff_base)  # noqa: S311  # nosec B311 -- jitter для retry backoff, не криптография
        await asyncio.sleep(base_delay + jitter)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """
        Внутренний метод для выполнения HTTP-запроса к Marzban.

        Добавляет базовую авторизацию admin-учёткой.
        Реализует ограниченный retry для транзиентных ошибок (сетевые сбои, 5xx).
        """
        req_headers: dict[str, str] = headers.copy() if headers else {}

        # Базовая авторизация admin-учёткой
        auth = (self._creds.username, self._creds.password)

        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.request(
                    method=method,
                    url=path,
                    json=json,
                    headers=req_headers,
                    auth=auth,
                )
            except httpx.RequestError as exc:
                err = MarzbanRequestError(f"Network error calling Marzban: {exc}")
                last_error = err
                self._logger.warning(
                    "marzban_request_network_error",
                    method=method,
                    path=path,
                    attempt=attempt,
                    max_retries=self._max_retries,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    await self._sleep_with_backoff(attempt)
                    continue
                raise err from exc

            # Ошибки аутентификации/авторизации не ретраим
            if resp.status_code in (401, 403):
                raise MarzbanAuthError(
                    f"Marzban auth failed: status={resp.status_code}, body={resp.text}"
                )

            # 5xx считаем транзиентными — пробуем повторить
            if resp.status_code >= 500:
                err = MarzbanRequestError(
                    f"Marzban server error: status={resp.status_code}, body={resp.text}",
                    status_code=resp.status_code,
                )
                last_error = err
                self._logger.warning(
                    "marzban_request_server_error",
                    method=method,
                    path=path,
                    status_code=resp.status_code,
                    attempt=attempt,
                    max_retries=self._max_retries,
                )
                if attempt < self._max_retries:
                    await self._sleep_with_backoff(attempt)
                    continue
                raise err

            # 4xx (кроме 401/403) — логическая ошибка, повторять бессмысленно
            if 400 <= resp.status_code < 500:
                raise MarzbanRequestError(
                    f"Marzban client error: status={resp.status_code}, body={resp.text}",
                    status_code=resp.status_code,
                )

            # Успешный ответ
            return resp

        # На всякий случай, если цикл завершится без return
        if last_error is not None:
            raise last_error
        raise MarzbanRequestError("Marzban request failed without specific error")

    def build_subscription_url(self, token: str) -> str:
        """
        Построить subscription URL для VPN-клиента.

        Базируется на XRAY_SUBSCRIPTION_URL_PREFIX и XRAY_SUBSCRIPTION_PATH
        (как они настроены в Marzban), но хранится на стороне FastLink.

        Примеры:
        - https://fastlinkproject.com/sub/<TOKEN>
        """
        # Здесь мы пока делаем допущение: префикс и path совпадают с продовой
        # конфигурацией, описанной в документации. При необходимости можно
        # вынести в Settings.
        prefix = "https://fastlinkproject.com"
        path = "/sub"

        return f"{prefix.rstrip('/')}{path}/{token}"

    def get_primary_config_link(self, user_info: MarzbanUserInfo) -> str | None:
        """Первая доступная конфиг-ссылка пользователя (для клиентов без поддержки subscription)."""
        return user_info.config_links[0] if user_info.config_links else None

    async def create_user(self, payload: MarzbanUserCreatePayload) -> MarzbanUserInfo:
        """
        Создать пользователя в Marzban.

        Ожидаемый контракт:
        - POST /users
        - body: username, inbound, data_limit_bytes, expiry_timestamp, enabled
        - ответ: JSON с данными пользователя
        """
        body = {
            "username": payload.username,
            "inbound": payload.inbound_tag,
            "data_limit_bytes": payload.data_limit_bytes,
            "expiry_timestamp": payload.expiry_timestamp,
            "enabled": payload.enabled,
        }

        resp = await self._request(
            method="POST",
            path="/users",
            json=body,
        )
        data = resp.json()

        return MarzbanUserInfo(
            username=data["username"],
            enabled=data.get("enabled", True),
            data_limit_bytes=data.get("data_limit_bytes", 0),
            data_used_bytes=data.get("data_used_bytes", 0),
            expiry_timestamp=data.get("expiry_timestamp"),
            config_links=list(data.get("links", [])),
        )

    async def get_user(self, username: str) -> MarzbanUserInfo:
        """
        Получить информацию о пользователе из Marzban.

        Ожидаемый контракт:
        - GET /users/{username}
        """
        resp = await self._request(
            method="GET",
            path=f"/users/{username}",
        )
        data = resp.json()

        return MarzbanUserInfo(
            username=data["username"],
            enabled=data.get("enabled", True),
            data_limit_bytes=data.get("data_limit_bytes", 0),
            data_used_bytes=data.get("data_used_bytes", 0),
            expiry_timestamp=data.get("expiry_timestamp"),
            config_links=list(data.get("links", [])),
        )

    async def set_user_traffic(
        self,
        username: str,
        *,
        data_used_bytes: int,
    ) -> None:
        """
        Обновить использованный трафик пользователя в Marzban.

        Привязано к Subscription.data_used_bytes.

        Ожидаемый контракт:
        - PATCH /users/{username}/traffic
        """
        body = {
            "data_used_bytes": data_used_bytes,
        }

        await self._request(
            method="PATCH",
            path=f"/users/{username}/traffic",
            json=body,
        )

    async def set_user_enabled(
        self,
        username: str,
        *,
        enabled: bool,
    ) -> None:
        """
        Включить/отключить пользователя в Marzban.

        Привязано к SubscriptionStatus.ACTIVE/DISABLED.
        """
        body = {
            "enabled": enabled,
        }

        await self._request(
            method="PATCH",
            path=f"/users/{username}/status",
            json=body,
        )
