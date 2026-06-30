from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress

import structlog
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from redis.asyncio import Redis

from config import get_deploy_commit_short, settings
from database.session import AsyncSessionFactory
from middlewares import DbSessionMiddleware, ThrottlingMiddleware, UserMiddleware
from handlers import router as root_router
from webhooks.test import test_webhook


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
    )


def setup_middlewares(dp: Dispatcher, redis_rate_limit: Redis) -> None:
    db_session_middleware = DbSessionMiddleware(session_factory=AsyncSessionFactory)
    user_middleware = UserMiddleware()
    throttling_middleware = ThrottlingMiddleware(redis=redis_rate_limit)

    dp.message.middleware(db_session_middleware)
    dp.callback_query.middleware(db_session_middleware)

    dp.message.middleware(user_middleware)
    dp.callback_query.middleware(user_middleware)

    dp.message.middleware(throttling_middleware)
    dp.callback_query.middleware(throttling_middleware)


async def healthcheck(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def telegram_webhook(request: web.Request) -> web.Response:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != settings.webhook_secret:
        return web.Response(status=403, text="forbidden")

    bot: Bot = request.app["bot"]
    dp: Dispatcher = request.app["dp"]

    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot=bot, update=update)
    except Exception:
        logger = structlog.get_logger(__name__)
        logger.exception("webhook_processing_error")

    return web.Response(status=200, text="ok")


async def on_startup(app: web.Application) -> None:
    logger = structlog.get_logger(__name__)
    bot: Bot = app["bot"]

    if settings.use_webhook and not settings.skip_webhook_registration:
        await bot.set_webhook(
            url=settings.webhook_url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
        )
        logger.info("webhook_registered", url=settings.webhook_url)
    else:
        logger.info("webhook_registration_skipped")


async def on_shutdown(app: web.Application) -> None:
    bot: Bot = app["bot"]
    redis_fsm: Redis = app["redis_fsm"]
    redis_rate_limit: Redis = app["redis_rate_limit"]

    with suppress(Exception):
        if settings.use_webhook:
            await bot.delete_webhook(drop_pending_updates=False)

    await bot.session.close()
    await redis_fsm.aclose()
    await redis_rate_limit.aclose()


async def run_webhook_mode() -> None:
    logger = structlog.get_logger(__name__)

    redis_fsm = Redis.from_url(settings.redis_url_fsm)
    redis_rate_limit = Redis.from_url(settings.redis_url_rate_limit)

    storage = RedisStorage(redis=redis_fsm)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=settings.bot_parse_mode),
    )
    dp = Dispatcher(storage=storage)
    setup_middlewares(dp, redis_rate_limit)
    dp.include_router(root_router)

    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp
    app["redis_fsm"] = redis_fsm
    app["redis_rate_limit"] = redis_rate_limit

    app.router.add_get(settings.healthcheck_url_path, healthcheck)
    app.router.add_post(settings.webhook_path, telegram_webhook)
    app.router.add_post("/webhook/test", test_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    logger.info(
        "bot_webhook_starting",
        host=settings.http_host,
        port=settings.http_port,
        health_path=settings.healthcheck_url_path,
        webhook_path=settings.webhook_path,
        deploy_commit_short=get_deploy_commit_short(),
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.http_host, port=settings.http_port)
    await site.start()

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await runner.cleanup()


async def run_polling_mode() -> None:
    redis_fsm = Redis.from_url(settings.redis_url_fsm)
    redis_rate_limit = Redis.from_url(settings.redis_url_rate_limit)

    storage = RedisStorage(redis=redis_fsm)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=settings.bot_parse_mode),
    )
    dp = Dispatcher(storage=storage)
    setup_middlewares(dp, redis_rate_limit)
    dp.include_router(root_router)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await redis_fsm.aclose()
        await redis_rate_limit.aclose()


async def main() -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    logger.info(
        "bot_starting",
        env=settings.app_env,
        use_webhook=settings.use_webhook,
        webhook_url=settings.webhook_url,
        deploy_commit_short=get_deploy_commit_short(),
    )

    if settings.use_webhook:
        await run_webhook_mode()
    else:
        await run_polling_mode()


if __name__ == "__main__":
    asyncio.run(main())
