from __future__ import annotations

import json
from typing import Any

import structlog
from aiohttp import web
from pydantic import ValidationError

from database.enums import WebhookEventStatus
from database.repo import WebhookEventsRepo
from database.session import get_async_session_factory
from schemas.yookassa import YooKassaNotificationPayload

logger = structlog.get_logger(__name__)


MAX_BODY_SIZE = 64 * 1024  # 64 KB, защита от слишком больших payload'ов


async def yookassa_webhook(request: web.Request) -> web.Response:
    # 1. Content-Type и размер
    if request.content_type != "application/json":
        return web.Response(status=415, text="unsupported media type")

    if request.content_length is not None and request.content_length > MAX_BODY_SIZE:
        return web.Response(status=413, text="payload too large")

    # 2. Чтение и базовая JSON-валидация
    try:
        raw_body = await request.text()
        data = json.loads(raw_body)
    except json.JSONDecodeError, UnicodeDecodeError:
        logger.warning("yookassa_webhook_invalid_json")
        return web.Response(status=400, text="invalid json")

    # 3. Pydantic-схема для строгой проверки
    try:
        payload = YooKassaNotificationPayload.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "yookassa_webhook_schema_validation_failed",
            errors=exc.errors(),
        )
        return web.Response(status=400, text="invalid payload")

    # 4. (будущая проверка подписи YooKassa)
    # signature = request.headers.get("X-Content-Signature")
    # if not verify_yookassa_signature(signature, raw_body, settings.yookassa_secret):
    #     return web.Response(status=401, text="invalid signature")

    provider = "yookassa"
    event_type = payload.event  # например, "payment.succeeded"
    external_id = payload.object.id  # ID платежа в YooKassa

    # 5. Нормализованный payload (строго по твоей схеме)
    normalized_payload: dict[str, Any] = payload.model_dump(mode="json")

    # 6. Сохранить событие в webhook_events
    factory = get_async_session_factory()
    async with factory() as session:
        repo = WebhookEventsRepo(session=session)
        event = await repo.create_event(
            provider=provider,
            event_type=event_type,
            external_id=external_id,
            idempotency_key=None,
            payload=normalized_payload,
            status=WebhookEventStatus.RECEIVED,
        )
        await session.commit()

    logger.info(
        "yookassa_webhook_enqueued",
        provider=provider,
        event_type=event_type,
        external_id=external_id,
        event_id=event.id,
    )

    # YooKassa ожидает 2xx. Достаточно 200 OK.
    return web.Response(status=200, text="ok")
