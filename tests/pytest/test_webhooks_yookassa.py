from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from database.enums import WebhookEventStatus
from webhooks.yookassa import yookassa_webhook


class _FakeSessionCM:
    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *exc: object) -> bool:
        return False


def factory_for(session: MagicMock):
    def factory():
        return _FakeSessionCM(session)

    return factory


def make_request(
    *,
    content_type: str = "application/json",
    content_length: int | None = 10,
    body: str = "{}",
    text_side_effect: BaseException | None = None,
) -> MagicMock:
    request = MagicMock(spec=web.Request)
    request.content_type = content_type
    request.content_length = content_length
    if text_side_effect is not None:
        request.text = AsyncMock(side_effect=text_side_effect)
    else:
        request.text = AsyncMock(return_value=body)
    return request


def valid_payload_json(
    *,
    event: str = "payment.succeeded",
    object_id: str = "yk-123456",
    status: str = "succeeded",
    paid: bool = True,
) -> str:
    return json.dumps(
        {
            "event": event,
            "object": {
                "id": object_id,
                "status": status,
                "amount": {"value": "100.00", "currency": "RUB"},
                "paid": paid,
                "created_at": "2026-08-23T00:00:00",
                "description": "FastLink payment #1",
                "metadata": {"subscription_id": "1"},
            },
        }
    )


# ---------------------------------------------------------------------------
# 1. Content-Type / размер
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_content_type_returns_415() -> None:
    request = make_request(content_type="text/plain")

    response = await yookassa_webhook(request)

    assert response.status == 415
    request.text.assert_not_awaited()


@pytest.mark.asyncio
async def test_payload_too_large_returns_413() -> None:
    request = make_request(content_length=64 * 1024 + 1)

    response = await yookassa_webhook(request)

    assert response.status == 413
    request.text.assert_not_awaited()


@pytest.mark.asyncio
async def test_content_length_none_is_allowed_through_size_check() -> None:
    """content_length может быть None (chunked/streaming) — размер тогда не
    проверяется на этом шаге, запрос идёт дальше к JSON-парсингу."""
    request = make_request(content_length=None, body="not-json{")

    response = await yookassa_webhook(request)

    request.text.assert_awaited_once()
    assert response.status == 400


# ---------------------------------------------------------------------------
# 2. JSON-валидация
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_json_returns_400() -> None:
    request = make_request(body="{not valid json")

    response = await yookassa_webhook(request)

    assert response.status == 400
    assert "invalid json" in response.text


@pytest.mark.asyncio
async def test_unicode_decode_error_returns_400() -> None:
    request = make_request(
        text_side_effect=UnicodeDecodeError(
            "utf-8", b"\xff", 0, 1, "invalid start byte"
        )
    )

    response = await yookassa_webhook(request)

    assert response.status == 400
    assert "invalid json" in response.text


# ---------------------------------------------------------------------------
# 3. Pydantic-валидация схемы
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_object_field_returns_400() -> None:
    request = make_request(body=json.dumps({"event": "payment.succeeded"}))

    response = await yookassa_webhook(request)

    assert response.status == 400
    assert "invalid payload" in response.text


@pytest.mark.asyncio
async def test_unknown_event_type_returns_400() -> None:
    """event не входит в YooKassaEvent Literal — pydantic должен отклонить."""
    request = make_request(body=valid_payload_json(event="payment.something_new"))

    response = await yookassa_webhook(request)

    assert response.status == 400
    assert "invalid payload" in response.text


@pytest.mark.asyncio
async def test_missing_required_amount_returns_400() -> None:
    body = json.dumps(
        {
            "event": "payment.succeeded",
            "object": {
                "id": "yk-1",
                "status": "succeeded",
                "paid": True,
            },
        }
    )
    request = make_request(body=body)

    response = await yookassa_webhook(request)

    assert response.status == 400
    assert "invalid payload" in response.text


# ---------------------------------------------------------------------------
# 4. Happy path — событие сохраняется в webhook_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_payload_persists_event_and_returns_200() -> None:
    request = make_request(body=valid_payload_json())
    session = MagicMock()
    session.commit = AsyncMock()
    repo = MagicMock()
    created_event = MagicMock(id=1)
    repo.create_event = AsyncMock(return_value=created_event)

    with (
        patch(
            "webhooks.yookassa.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("webhooks.yookassa.WebhookEventsRepo", return_value=repo),
    ):
        response = await yookassa_webhook(request)

    assert response.status == 200
    assert response.text == "ok"
    session.commit.assert_awaited_once()
    repo.create_event.assert_awaited_once()
    call_kwargs = repo.create_event.await_args.kwargs
    assert call_kwargs["provider"] == "yookassa"
    assert call_kwargs["event_type"] == "payment.succeeded"
    assert call_kwargs["external_id"] == "yk-123456"
    assert call_kwargs["idempotency_key"] is None
    assert call_kwargs["status"] == WebhookEventStatus.RECEIVED
    assert call_kwargs["payload"]["event"] == "payment.succeeded"
    assert call_kwargs["payload"]["object"]["id"] == "yk-123456"


@pytest.mark.asyncio
async def test_valid_refund_event_persists_with_correct_event_type() -> None:
    request = make_request(
        body=valid_payload_json(event="refund.succeeded", object_id="yk-refund-1")
    )
    session = MagicMock()
    session.commit = AsyncMock()
    repo = MagicMock()
    repo.create_event = AsyncMock(return_value=MagicMock(id=2))

    with (
        patch(
            "webhooks.yookassa.get_async_session_factory",
            return_value=factory_for(session),
        ),
        patch("webhooks.yookassa.WebhookEventsRepo", return_value=repo),
    ):
        response = await yookassa_webhook(request)

    assert response.status == 200
    call_kwargs = repo.create_event.await_args.kwargs
    assert call_kwargs["event_type"] == "refund.succeeded"
    assert call_kwargs["external_id"] == "yk-refund-1"
