from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import (
    build_bot_and_dispatcher,
    on_shutdown,
    on_startup,
    setup_middlewares,
    telegram_webhook,
)


def make_settings(**overrides) -> SimpleNamespace:
    defaults = {
        "redis_url_fsm": "redis://localhost:6379/0",
        "redis_url_rate_limit": "redis://localhost:6379/1",
        "bot_token": "test-bot-token",
        "bot_parse_mode": "HTML",
        "support_bot_token": None,
        "webhook_secret": "secret123",
        "webhook_path": "/webhook",
        "healthcheck_url_path": "/health",
        "use_webhook": True,
        "skip_webhook_registration": False,
        "webhook_url": "https://example.com/webhook",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_bot_mock(username: str | None = "mainbot") -> MagicMock:
    b = MagicMock()
    me = MagicMock(username=username)
    b.get_me = AsyncMock(return_value=me)
    b.session = MagicMock()
    b.session.close = AsyncMock()
    b.set_webhook = AsyncMock()
    b.delete_webhook = AsyncMock()
    return b


# ---------------------------------------------------------------------------
# setup_middlewares
# ---------------------------------------------------------------------------


def test_setup_middlewares_registers_all_five_on_message_and_callback() -> None:
    dp = MagicMock()
    redis_rate_limit = MagicMock()

    with (
        patch("bot.DbSessionMiddleware", return_value=MagicMock()),
        patch("bot.UserMiddleware", return_value=MagicMock()),
        patch("bot.ThrottlingMiddleware", return_value=MagicMock()),
        patch("bot.LoggingMiddleware", return_value=MagicMock()),
        patch("bot.AdminSessionMiddleware", return_value=MagicMock()),
        patch("bot.get_async_session_factory", return_value=MagicMock()),
    ):
        setup_middlewares(dp, redis_rate_limit)

    assert dp.message.middleware.call_count == 5
    assert dp.callback_query.middleware.call_count == 5


# ---------------------------------------------------------------------------
# build_bot_and_dispatcher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_bot_and_dispatcher_happy_path_no_support_bot() -> None:
    settings_obj = make_settings(support_bot_token=None)
    main_bot = make_bot_mock(username="mainbot")
    dp_mock = MagicMock()

    with (
        patch("bot.settings", settings_obj),
        patch("bot.Redis") as redis_cls,
        patch("bot.RedisStorage", return_value=MagicMock()),
        patch("bot.Bot", return_value=main_bot),
        patch("bot.Dispatcher", return_value=dp_mock),
        patch("bot.setup_middlewares") as setup_mw,
        patch("bot.set_bot_username") as set_bot_username_mock,
        patch("bot.set_support_bot_username") as set_support_bot_username_mock,
    ):
        redis_cls.from_url = MagicMock(side_effect=[MagicMock(), MagicMock()])
        _redis_fsm, redis_rate_limit, bot, dp = await build_bot_and_dispatcher()

    assert bot is main_bot
    assert dp is dp_mock
    set_bot_username_mock.assert_called_once_with("mainbot")
    set_support_bot_username_mock.assert_not_called()
    setup_mw.assert_called_once_with(dp_mock, redis_rate_limit)
    dp_mock.include_router.assert_called_once()


@pytest.mark.asyncio
async def test_build_bot_and_dispatcher_no_username_raises_runtime_error() -> None:
    settings_obj = make_settings(support_bot_token=None)
    main_bot = make_bot_mock(username=None)

    with (
        patch("bot.settings", settings_obj),
        patch("bot.Redis") as redis_cls,
        patch("bot.RedisStorage", return_value=MagicMock()),
        patch("bot.Bot", return_value=main_bot),
        patch("bot.Dispatcher", return_value=MagicMock()),
        patch("bot.setup_middlewares"),
    ):
        redis_cls.from_url = MagicMock(side_effect=[MagicMock(), MagicMock()])
        with pytest.raises(RuntimeError, match="no username"):
            await build_bot_and_dispatcher()


@pytest.mark.asyncio
async def test_build_bot_and_dispatcher_resolves_support_bot_username() -> None:
    settings_obj = make_settings(support_bot_token="support-token")
    main_bot = make_bot_mock(username="mainbot")
    support_bot = make_bot_mock(username="supportbot")

    with (
        patch("bot.settings", settings_obj),
        patch("bot.Redis") as redis_cls,
        patch("bot.RedisStorage", return_value=MagicMock()),
        patch("bot.Bot", side_effect=[main_bot, support_bot]),
        patch("bot.Dispatcher", return_value=MagicMock()),
        patch("bot.setup_middlewares"),
        patch("bot.set_bot_username"),
        patch("bot.set_support_bot_username") as set_support_bot_username_mock,
    ):
        redis_cls.from_url = MagicMock(side_effect=[MagicMock(), MagicMock()])
        await build_bot_and_dispatcher()

    set_support_bot_username_mock.assert_called_once_with("supportbot")
    support_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_bot_and_dispatcher_support_bot_no_username_warns() -> None:
    settings_obj = make_settings(support_bot_token="support-token")
    main_bot = make_bot_mock(username="mainbot")
    support_bot = make_bot_mock(username=None)

    with (
        patch("bot.settings", settings_obj),
        patch("bot.Redis") as redis_cls,
        patch("bot.RedisStorage", return_value=MagicMock()),
        patch("bot.Bot", side_effect=[main_bot, support_bot]),
        patch("bot.Dispatcher", return_value=MagicMock()),
        patch("bot.setup_middlewares"),
        patch("bot.set_bot_username"),
        patch("bot.set_support_bot_username") as set_support_bot_username_mock,
    ):
        redis_cls.from_url = MagicMock(side_effect=[MagicMock(), MagicMock()])
        await build_bot_and_dispatcher()

    set_support_bot_username_mock.assert_not_called()
    support_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_bot_and_dispatcher_support_bot_get_me_fails_is_swallowed() -> None:
    settings_obj = make_settings(support_bot_token="support-token")
    main_bot = make_bot_mock(username="mainbot")
    support_bot = make_bot_mock(username="supportbot")
    support_bot.get_me = AsyncMock(side_effect=Exception("telegram api down"))

    with (
        patch("bot.settings", settings_obj),
        patch("bot.Redis") as redis_cls,
        patch("bot.RedisStorage", return_value=MagicMock()),
        patch("bot.Bot", side_effect=[main_bot, support_bot]),
        patch("bot.Dispatcher", return_value=MagicMock()),
        patch("bot.setup_middlewares"),
        patch("bot.set_bot_username"),
        patch("bot.set_support_bot_username") as set_support_bot_username_mock,
    ):
        redis_cls.from_url = MagicMock(side_effect=[MagicMock(), MagicMock()])
        _redis_fsm, _redis_rate_limit, bot, _dp = await build_bot_and_dispatcher()

    set_support_bot_username_mock.assert_not_called()
    support_bot.session.close.assert_awaited_once()
    assert bot is main_bot


# ---------------------------------------------------------------------------
# telegram_webhook
# ---------------------------------------------------------------------------


def make_webhook_request(
    *, secret: str, bot: MagicMock, dp: MagicMock, json_data=None, json_side_effect=None
):
    request = MagicMock()
    request.headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
    request.app = {}
    from bot import BOT_KEY, DP_KEY

    request.app[BOT_KEY] = bot
    request.app[DP_KEY] = dp
    if json_side_effect is not None:
        request.json = AsyncMock(side_effect=json_side_effect)
    else:
        request.json = AsyncMock(return_value=json_data or {})
    return request


@pytest.mark.asyncio
async def test_telegram_webhook_wrong_secret_returns_403() -> None:
    settings_obj = make_settings(webhook_secret="correct-secret")
    request = make_webhook_request(
        secret="wrong-secret", bot=MagicMock(), dp=MagicMock()
    )

    with patch("bot.settings", settings_obj):
        response = await telegram_webhook(request)

    assert response.status == 403


@pytest.mark.asyncio
async def test_telegram_webhook_valid_update_feeds_dispatcher() -> None:
    settings_obj = make_settings(webhook_secret="correct-secret")
    bot_mock = MagicMock()
    dp_mock = MagicMock()
    dp_mock.feed_update = AsyncMock()
    update_payload = {"update_id": 1}
    request = make_webhook_request(
        secret="correct-secret", bot=bot_mock, dp=dp_mock, json_data=update_payload
    )

    with (
        patch("bot.settings", settings_obj),
        patch("bot.Update") as update_cls,
    ):
        update_cls.model_validate = MagicMock(return_value=MagicMock())
        response = await telegram_webhook(request)

    dp_mock.feed_update.assert_awaited_once()
    assert response.status == 200


@pytest.mark.asyncio
async def test_telegram_webhook_malformed_update_still_returns_200() -> None:
    settings_obj = make_settings(webhook_secret="correct-secret")
    bot_mock = MagicMock()
    dp_mock = MagicMock()
    dp_mock.feed_update = AsyncMock()
    request = make_webhook_request(
        secret="correct-secret",
        bot=bot_mock,
        dp=dp_mock,
        json_side_effect=ValueError("bad json"),
    )

    with patch("bot.settings", settings_obj):
        response = await telegram_webhook(request)

    dp_mock.feed_update.assert_not_awaited()
    assert response.status == 200


# ---------------------------------------------------------------------------
# on_startup
# ---------------------------------------------------------------------------


def make_app_with_bot(bot: MagicMock) -> dict:
    from bot import BOT_KEY

    return {BOT_KEY: bot}


@pytest.mark.asyncio
async def test_on_startup_registers_webhook_when_enabled() -> None:
    settings_obj = make_settings(
        use_webhook=True,
        skip_webhook_registration=False,
        webhook_url="https://example.com/webhook",
        webhook_secret="secret123",
    )
    bot_mock = make_bot_mock()
    app = make_app_with_bot(bot_mock)

    with patch("bot.settings", settings_obj):
        await on_startup(app)

    bot_mock.set_webhook.assert_awaited_once_with(
        url="https://example.com/webhook",
        secret_token="secret123",
        drop_pending_updates=True,
    )


@pytest.mark.asyncio
async def test_on_startup_skips_when_use_webhook_false() -> None:
    settings_obj = make_settings(use_webhook=False)
    bot_mock = make_bot_mock()
    app = make_app_with_bot(bot_mock)

    with patch("bot.settings", settings_obj):
        await on_startup(app)

    bot_mock.set_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_startup_skips_when_skip_flag_set() -> None:
    settings_obj = make_settings(use_webhook=True, skip_webhook_registration=True)
    bot_mock = make_bot_mock()
    app = make_app_with_bot(bot_mock)

    with patch("bot.settings", settings_obj):
        await on_startup(app)

    bot_mock.set_webhook.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_shutdown
# ---------------------------------------------------------------------------


def make_app_full(
    bot: MagicMock, redis_fsm: MagicMock, redis_rate_limit: MagicMock
) -> dict:
    from bot import BOT_KEY, REDIS_FSM_KEY, REDIS_RATE_LIMIT_KEY

    return {
        BOT_KEY: bot,
        REDIS_FSM_KEY: redis_fsm,
        REDIS_RATE_LIMIT_KEY: redis_rate_limit,
    }


@pytest.mark.asyncio
async def test_on_shutdown_deletes_webhook_and_closes_everything() -> None:
    settings_obj = make_settings(use_webhook=True)
    bot_mock = make_bot_mock()
    redis_fsm = MagicMock()
    redis_fsm.aclose = AsyncMock()
    redis_rate_limit = MagicMock()
    redis_rate_limit.aclose = AsyncMock()
    app = make_app_full(bot_mock, redis_fsm, redis_rate_limit)

    with patch("bot.settings", settings_obj):
        await on_shutdown(app)

    bot_mock.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
    bot_mock.session.close.assert_awaited_once()
    redis_fsm.aclose.assert_awaited_once()
    redis_rate_limit.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_shutdown_skips_delete_webhook_when_not_using_webhook() -> None:
    settings_obj = make_settings(use_webhook=False)
    bot_mock = make_bot_mock()
    redis_fsm = MagicMock()
    redis_fsm.aclose = AsyncMock()
    redis_rate_limit = MagicMock()
    redis_rate_limit.aclose = AsyncMock()
    app = make_app_full(bot_mock, redis_fsm, redis_rate_limit)

    with patch("bot.settings", settings_obj):
        await on_shutdown(app)

    bot_mock.delete_webhook.assert_not_awaited()
    bot_mock.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_shutdown_suppresses_delete_webhook_failure() -> None:
    settings_obj = make_settings(use_webhook=True)
    bot_mock = make_bot_mock()
    bot_mock.delete_webhook = AsyncMock(side_effect=Exception("telegram down"))
    redis_fsm = MagicMock()
    redis_fsm.aclose = AsyncMock()
    redis_rate_limit = MagicMock()
    redis_rate_limit.aclose = AsyncMock()
    app = make_app_full(bot_mock, redis_fsm, redis_rate_limit)

    with patch("bot.settings", settings_obj):
        await on_shutdown(app)

    bot_mock.session.close.assert_awaited_once()
    redis_fsm.aclose.assert_awaited_once()
    redis_rate_limit.aclose.assert_awaited_once()
