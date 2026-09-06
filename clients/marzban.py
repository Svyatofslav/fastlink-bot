from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

import httpx
import structlog
from redis.asyncio import Redis

from config import get_settings

_TOKEN_CACHE_KEY = "marzban:admin_token"  # noqa: S105 — ключ кеша, не секрет  # nosec B105

# Единственный протокол, который использует FastLink сейчас — VLESS+Reality.
# Inbound создаётся вручную в панели Marzban (см. Server.inbound_tag).
_PROXY_PROTOCOL = "vless"


@dataclass(frozen=True)
class MarzbanCredentials:
    """
    Базовые учётные данные для доступа к Marzban API.

    api_base — полный базовый URL, включая /api (см. MARZBAN_API_BASE
    в Settings), например "http://host.docker.internal:8000/api".
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
        self.status_code = status_code


@dataclass(frozen=True)
class MarzbanUserCreatePayload:
    """
    DTO для создания пользователя в Marzban.

    Форма DTO стабильна — реальный формат запроса к Marzban API собирается
    внутри MarzbanClient.create_user(), вызывающий код этой детали не знает.
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

    subscription_url — готовая ссылка, которую формирует сам Marzban
    (не пересобирается на нашей стороне).
    """

    username: str
    enabled: bool
    data_limit_bytes: int
    data_used_bytes: int
    expiry_timestamp: int | None
    subscription_url: str = ""
    config_links: list[str] = field(default_factory=list)


class MarzbanClient:
    """
    Async-клиент для работы с Marzban API.

    Аутентификация — OAuth2 password flow (POST {api_base}/admin/token),
    Bearer-токен кешируется в Redis (REDIS_URL_MARZBAN_TOKEN) между
    вызовами. URL всегда собирается явной конкатенацией api_base + путь —
    без опоры на автоматическую склейку httpx (base_url), чтобы не зависеть
    от тонкостей RFC 3986 при относительных/абсолютных путях.
    """

    def __init__(
        self,
        credentials: MarzbanCredentials | None = None,
        *,
        token_cache: Redis | None = None,
    ) -> None:
        settings = get_settings()

        if credentials is None:
            credentials = MarzbanCredentials(
                api_base=settings.marzban_api_base,
                username=settings.marzban_username,
                password=settings.marzban_password,
                timeout_seconds=settings.marzban_timeout_seconds,
            )

        self._creds = credentials
        self._api_base = credentials.api_base.rstrip("/")
        self._max_retries = settings.marzban_max_retries
        self._backoff_base = settings.marzban_backoff_base_seconds
        self._token_ttl_seconds = settings.marzban_token_ttl_seconds
        self._logger = structlog.get_logger(__name__)

        self._owns_token_cache = token_cache is None
        self._token_cache = token_cache or Redis.from_url(
            settings.redis_url_marzban_token
        )

        # base_url намеренно не задаём — URL собираем сами в _build_url(),
        # чтобы не зависеть от правил склейки httpx (RFC 3986: абсолютный
        # путь в request(url=...) полностью отбрасывает путь из base_url).
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._creds.timeout_seconds),
        )

    def _build_url(self, path: str) -> str:
        return f"{self._api_base}/{path.lstrip('/')}"

    async def aclose(self) -> None:
        """Закрыть HTTP-клиент и (если создан этим инстансом) Redis-соединение."""
        await self._client.aclose()
        if self._owns_token_cache:
            await self._token_cache.aclose()

    async def _sleep_with_backoff(self, attempt: int) -> None:
        base_delay = self._backoff_base * (2**attempt)
        # jitter для retry backoff, не криптография — random здесь допустим
        jitter = random.uniform(0, self._backoff_base)  # noqa: S311  # nosec B311
        await asyncio.sleep(base_delay + jitter)

    async def _fetch_new_token(self) -> str:
        """POST {api_base}/admin/token — OAuth2 password flow, form-encoded body."""
        try:
            resp = await self._client.post(
                self._build_url("admin/token"),
                data={
                    "username": self._creds.username,
                    "password": self._creds.password,
                    "grant_type": "password",
                },
            )
        except httpx.RequestError as exc:
            raise MarzbanRequestError(
                f"Network error fetching Marzban admin token: {exc}"
            ) from exc

        if resp.status_code in (401, 403):
            raise MarzbanAuthError(
                f"Marzban admin auth failed: status={resp.status_code}, "
                f"body={resp.text}"
            )
        if resp.status_code >= 400:
            raise MarzbanRequestError(
                f"Marzban token request failed: status={resp.status_code}, "
                f"body={resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise MarzbanRequestError(f"Malformed Marzban token response: {data}")
        return str(token)

    async def _get_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh:
            cached = await self._token_cache.get(_TOKEN_CACHE_KEY)
            if cached is not None:
                return cached.decode() if isinstance(cached, bytes) else cached

        token = await self._fetch_new_token()
        await self._token_cache.set(_TOKEN_CACHE_KEY, token, ex=self._token_ttl_seconds)
        return token

    async def _send_once(
        self,
        method: str,
        url: str,
        *,
        json: dict | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        """Один HTTP-вызов; сетевые ошибки оборачивает в MarzbanRequestError."""
        try:
            return await self._client.request(
                method=method, url=url, json=json, headers=headers
            )
        except httpx.RequestError as exc:
            raise MarzbanRequestError(f"Network error calling Marzban: {exc}") from exc

    def _server_error(
        self, resp: httpx.Response, *, method: str, path: str, attempt: int
    ) -> MarzbanRequestError:
        self._logger.warning(
            "marzban_request_server_error",
            method=method,
            path=path,
            status_code=resp.status_code,
            attempt=attempt,
            max_retries=self._max_retries,
        )
        return MarzbanRequestError(
            f"Marzban server error: status={resp.status_code}, body={resp.text}",
            status_code=resp.status_code,
        )

    def _raise_for_client_error(self, resp: httpx.Response) -> None:
        if 400 <= resp.status_code < 500:
            raise MarzbanRequestError(
                f"Marzban client error: status={resp.status_code}, body={resp.text}",
                status_code=resp.status_code,
            )

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

        Подставляет Bearer-токен из кеша. При 401/403 один раз форсирует
        обновление токена и повторяет запрос (на случай устаревшего кеша) —
        эта попытка НЕ расходует общий бюджет max_retries, у неё отдельный
        флаг auth_retried. Реализует ограниченный retry для сетевых сбоев
        и 5xx в рамках max_retries.
        """
        req_headers: dict[str, str] = headers.copy() if headers else {}
        url = self._build_url(path)
        last_error: Exception | None = None
        auth_retried = False
        attempt = 0

        while attempt <= self._max_retries:
            token = await self._get_token()
            req_headers["Authorization"] = f"Bearer {token}"

            try:
                resp = await self._send_once(
                    method, url, json=json, headers=req_headers
                )
            except MarzbanRequestError as exc:
                last_error = exc
                self._logger.warning(
                    "marzban_request_network_error",
                    method=method,
                    path=path,
                    attempt=attempt,
                    max_retries=self._max_retries,
                    error=str(exc),
                )
                if attempt >= self._max_retries:
                    raise
                await self._sleep_with_backoff(attempt)
                attempt += 1
                continue

            if resp.status_code in (401, 403):
                if auth_retried:
                    raise MarzbanAuthError(
                        f"Marzban auth failed: status={resp.status_code}, "
                        f"body={resp.text}"
                    )
                auth_retried = True
                await self._get_token(force_refresh=True)
                continue  # не увеличиваем attempt — это не сетевая попытка

            if resp.status_code >= 500:
                last_error = self._server_error(
                    resp, method=method, path=path, attempt=attempt
                )
                if attempt >= self._max_retries:
                    raise last_error
                await self._sleep_with_backoff(attempt)
                attempt += 1
                continue

            self._raise_for_client_error(resp)
            return resp

        if last_error is not None:
            raise last_error  # pragma: no cover — структурно недостижимо: каждая
            # ветка ошибки либо raise'ит сама при attempt >= max_retries до выхода
            # из цикла, либо continue только при attempt < max_retries (цикл
            # продолжится, а не завершится с last_error != None)
        raise MarzbanRequestError("Marzban request failed without specific error")

    def _parse_user_info(self, data: dict) -> MarzbanUserInfo:
        """Собрать MarzbanUserInfo из реального ответа Marzban (UserResponse)."""
        return MarzbanUserInfo(
            username=data["username"],
            enabled=data.get("status") == "active",
            data_limit_bytes=data.get("data_limit") or 0,
            data_used_bytes=data.get("used_traffic", 0),
            expiry_timestamp=data.get("expire"),
            subscription_url=data.get("subscription_url", ""),
            config_links=list(data.get("links", [])),
        )

    def get_primary_config_link(self, user_info: MarzbanUserInfo) -> str | None:
        """Первая доступная конфиг-ссылка (для клиентов без поддержки subscription)."""
        return user_info.config_links[0] if user_info.config_links else None

    async def create_user(self, payload: MarzbanUserCreatePayload) -> MarzbanUserInfo:
        """
        Создать пользователя в Marzban.

        Реальный контракт: POST {api_base}/user
        body: username, proxies, inbounds, data_limit, expire, status
        """
        body = {
            "username": payload.username,
            "proxies": {_PROXY_PROTOCOL: {}},
            "inbounds": {_PROXY_PROTOCOL: [payload.inbound_tag]},
            "data_limit": payload.data_limit_bytes,
            "expire": payload.expiry_timestamp,
            "status": "active" if payload.enabled else "on_hold",
        }
        resp = await self._request(method="POST", path="user", json=body)
        return self._parse_user_info(resp.json())

    async def get_user(self, username: str) -> MarzbanUserInfo:
        """GET {api_base}/user/{username} — актуальные данные, включая used_traffic."""
        resp = await self._request(method="GET", path=f"user/{username}")
        return self._parse_user_info(resp.json())

    async def update_user(
        self,
        username: str,
        *,
        data_limit_bytes: int | None = None,
        expiry_timestamp: int | None = None,
        enabled: bool | None = None,
    ) -> MarzbanUserInfo:
        """
        Частично изменить пользователя в Marzban: PUT /api/user/{username}.
        Поля, не переданные (None), Marzban не трогает — это официально
        задокументированное поведение UserModify.
        """
        body: dict[str, int | str] = {}
        if data_limit_bytes is not None:
            body["data_limit"] = data_limit_bytes
        if expiry_timestamp is not None:
            body["expire"] = expiry_timestamp
        if enabled is not None:
            body["status"] = "active" if enabled else "disabled"
        resp = await self._request(method="PUT", path=f"user/{username}", json=body)
        return self._parse_user_info(resp.json())
