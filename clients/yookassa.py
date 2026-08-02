from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import structlog

from config import get_settings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class YooKassaCredentials:
    """Учётные данные YooKassa API (shop_id + secret_key)."""

    shop_id: str
    secret_key: str
    api_base: str = "https://api.yookassa.ru/v3"
    timeout_seconds: int = 15


class YooKassaClientError(Exception):
    """Базовое исключение клиента YooKassa."""


@dataclass(frozen=True)
class YooKassaPaymentLink:
    """
    Результат создания платежа в YooKassa.

    provider_payment_id — id платежа на стороне YooKassa, используется
    как внешний идентификатор для сверки в webhook (payment.succeeded).
    confirmation_url — ссылка, на которую отправляем пользователя для оплаты.
    """

    provider_payment_id: str
    confirmation_url: str


class YooKassaClient:
    """
    Тонкий async-клиент для создания платежей в YooKassa.

    Инкапсулирует HTTP-детали (Basic Auth, Idempotence-Key header,
    формат payload), чтобы PaymentService не знал о REST API YooKassa
    напрямую — только о методе create_payment_link().
    """

    def __init__(self, credentials: YooKassaCredentials | None = None) -> None:
        settings = get_settings()
        if credentials is None:
            credentials = YooKassaCredentials(
                shop_id=settings.yookassa_shop_id,
                secret_key=settings.yookassa_secret_key,
            )
        self.creds = credentials
        self.client = httpx.AsyncClient(
            base_url=self.creds.api_base,
            timeout=httpx.Timeout(self.creds.timeout_seconds),
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def create_payment_link(
        self,
        *,
        amount: int,
        currency: str,
        description: str,
        idempotency_key: str,
        return_url: str,
        metadata: dict | None = None,
    ) -> YooKassaPaymentLink:
        """
        Создаёт платёж в YooKassa и возвращает ссылку на оплату.

        amount передаётся в минимальных единицах (копейках) — конвертация
        в рубли (major units) происходит здесь, YooKassa API ожидает строку
        с двумя знаками после запятой в major units.

        idempotency_key передаётся в заголовке Idempotence-Key — при
        повторном вызове с тем же ключом YooKassa вернёт тот же платёж
        вместо создания дубля (это работает независимо от нашей
        собственной идемпотентности на уровне БД, как дополнительный
        уровень защиты на стороне провайдера).
        """
        amount_major = f"{amount / 100:.2f}"
        body = {
            "amount": {"value": amount_major, "currency": currency},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": metadata or {},
        }
        headers = {"Idempotence-Key": idempotency_key}

        try:
            resp = await self.client.post(
                "/payments",
                json=body,
                headers=headers,
                auth=(self.creds.shop_id, self.creds.secret_key),
            )
        except httpx.RequestError as exc:
            raise YooKassaClientError(f"Network error calling YooKassa: {exc}") from exc

        if resp.status_code >= 400:
            logger.warning(
                "yookassa_create_payment_failed",
                status_code=resp.status_code,
                body=resp.text,
            )
            raise YooKassaClientError(
                f"YooKassa create payment failed: status={resp.status_code} body={resp.text}"
            )

        data = resp.json()
        provider_payment_id = data.get("id")
        confirmation_url = data.get("confirmation", {}).get("confirmation_url")

        if not provider_payment_id or not confirmation_url:
            raise YooKassaClientError(f"Malformed YooKassa response: {data}")

        return YooKassaPaymentLink(
            provider_payment_id=provider_payment_id,
            confirmation_url=confirmation_url,
        )


class FakeYooKassaClient(YooKassaClient):
    """
    Заглушка для окружений без реального доступа к YooKassa
    (локальная разработка, тесты, текущая фаза без ключей).

    Не делает HTTP-запросов — сразу возвращает предсказуемую ссылку.
    Переключение между реальным и фейковым клиентом делается через
    настройку settings.yookassa_enabled (или аналогичный флаг),
    а не через прямой импорт в хендлерах.
    """

    def __init__(self) -> None:
        # super().__init__ не нужен, нет httpx.client
        pass

    async def aclose(self) -> None:
        return None

    async def create_payment_link(
        self,
        *,
        amount: int,
        currency: str,
        description: str,
        idempotency_key: str,
        return_url: str,
        metadata: dict | None = None,
    ) -> YooKassaPaymentLink:
        del amount, currency, description, idempotency_key, return_url, metadata

        fake_id = f"fake_{uuid.uuid4().hex[:12]}"
        return YooKassaPaymentLink(
            provider_payment_id=fake_id,
            confirmation_url="https://example.com/PLACEHOLDER",
        )
