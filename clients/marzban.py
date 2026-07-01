from __future__ import annotations

from dataclasses import dataclass

import httpx

from config import get_settings


@dataclass(frozen=True)
class MarzbanCredentials:
    """
    Базовые учётные данные для доступа к Marzban API.

    По умолчанию используем admin-логин/пароль из Settings.
    Для отдельных серверов можем подставлять отдельный API-токен.
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


class MarzbanClient:
    """
    Async-клиент для работы с Marzban API.

    Использует httpx.AsyncClient, базовый URL и таймаут из Settings.
    Не хранит токены сервера — их выдаёт ServerRepo.get_server_secrets.
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
        self._client = httpx.AsyncClient(
            base_url=self._creds.api_base.rstrip("/"),
            timeout=httpx.Timeout(self._creds.timeout_seconds),
        )

    async def aclose(self) -> None:
        """
        Закрыть HTTP-клиент (вызывать при остановке приложения/worker).
        """
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        headers: dict | None = None,
        server_api_token: str | None = None,
    ) -> httpx.Response:
        """
        Внутренний метод для выполнения HTTP-запроса к Marzban.

        Добавляет базовую авторизацию и, при необходимости,
        bearer-токен конкретного сервера.
        """
        req_headers: dict[str, str] = headers.copy() if headers else {}

        # Базовая авторизация admin-учёткой
        auth = (self._creds.username, self._creds.password)

        # Дополнительный Bearer-токен для конкретного сервера (если есть)
        if server_api_token:
            req_headers.setdefault("Authorization", f"Bearer {server_api_token}")

        try:
            resp = await self._client.request(
                method=method,
                url=path,
                json=json,
                headers=req_headers,
                auth=auth,
            )
        except httpx.RequestError as exc:
            raise MarzbanRequestError(f"Network error calling Marzban: {exc}") from exc

        if resp.status_code in (401, 403):
            raise MarzbanAuthError(
                f"Marzban auth failed: status={resp.status_code}, body={resp.text}"
            )

        if resp.is_client_error or resp.is_server_error:
            raise MarzbanRequestError(
                f"Marzban error: status={resp.status_code}, body={resp.text}"
            )

        return resp

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


class MarzbanClient(MarzbanClient):  # продолжаем существующий класс
    async def create_user(
        self,
        payload: MarzbanUserCreatePayload,
        *,
        server_api_token: str | None = None,
    ) -> MarzbanUserInfo:
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
            server_api_token=server_api_token,
        )
        data = resp.json()

        return MarzbanUserInfo(
            username=data["username"],
            enabled=data.get("enabled", True),
            data_limit_bytes=data.get("data_limit_bytes", 0),
            data_used_bytes=data.get("data_used_bytes", 0),
            expiry_timestamp=data.get("expiry_timestamp"),
        )

    async def get_user(
        self,
        username: str,
        *,
        server_api_token: str | None = None,
    ) -> MarzbanUserInfo:
        """
        Получить информацию о пользователе из Marzban.

        Ожидаемый контракт:
        - GET /users/{username}
        """
        resp = await self._request(
            method="GET",
            path=f"/users/{username}",
            server_api_token=server_api_token,
        )
        data = resp.json()

        return MarzbanUserInfo(
            username=data["username"],
            enabled=data.get("enabled", True),
            data_limit_bytes=data.get("data_limit_bytes", 0),
            data_used_bytes=data.get("data_used_bytes", 0),
            expiry_timestamp=data.get("expiry_timestamp"),
        )

    async def set_user_traffic(
        self,
        username: str,
        *,
        data_used_bytes: int,
        server_api_token: str | None = None,
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
            server_api_token=server_api_token,
        )

    async def set_user_enabled(
        self,
        username: str,
        *,
        enabled: bool,
        server_api_token: str | None = None,
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
            server_api_token=server_api_token,
        )
