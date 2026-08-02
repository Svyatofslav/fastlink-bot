from unittest.mock import MagicMock

import pytest

from bot import build_app, healthcheck


@pytest.mark.asyncio
async def test_healthcheck_returns_status_ok():
    resp = await healthcheck(MagicMock())
    assert resp.status == 200


def test_build_app_registers_core_routes_without_telegram_webhook():
    app = build_app(
        bot=MagicMock(),
        dp=MagicMock(),
        redis_fsm=MagicMock(),
        redis_rate_limit=MagicMock(),
        include_telegram_webhook=False,
    )
    paths = [r.resource.canonical for r in app.router.routes()]
    assert any("health" in p for p in paths)
    assert any("test" in p for p in paths)


def test_build_app_includes_telegram_webhook_when_requested():
    app = build_app(
        bot=MagicMock(),
        dp=MagicMock(),
        redis_fsm=MagicMock(),
        redis_rate_limit=MagicMock(),
        include_telegram_webhook=True,
    )
    paths = [r.resource.canonical for r in app.router.routes()]
    from config import settings

    assert settings.webhook_path in "".join(paths)
