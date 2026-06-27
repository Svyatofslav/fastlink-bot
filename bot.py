from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
import structlog

from config import deploy_commit_short, settings


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


async def healthcheck(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def telegram_webhook(request: web.Request) -> web.Response:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != settings.webhook_secret:
        return web.Response(status=403, text="forbidden")
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
    redis: Redis = app["redis"]

    with suppress(Exception):
        if settings.use_webhook:
            await bot.delete_webhook(drop_pending_updates=False)

    await bot.session.close()
    await redis.aclose()


async def run_webhook_mode() -> None:
    logger = structlog.get_logger(__name__)

    redis = Redis.from_url(settings.redis_url_fsm)
    storage = RedisStorage(redis=redis)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=settings.bot_parse_mode),
    )
    dp = Dispatcher(storage=storage)

    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp
    app["redis"] = redis

    app.router.add_get(settings.healthcheck_url_path, healthcheck)
    app.router.add_post(settings.webhook_path, telegram_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    logger.info(
        "bot_webhook_starting",
        host=settings.http_host,
        port=settings.http_port,
        health_path=settings.healthcheck_url_path,
        webhook_path=settings.webhook_path,
        deploy_commit_short=deploy_commit_short,
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
    redis = Redis.from_url(settings.redis_url_fsm)
    storage = RedisStorage(redis=redis)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=settings.bot_parse_mode),
    )
    dp = Dispatcher(storage=storage)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await redis.aclose()


async def main() -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    logger.info(
        "bot_starting",
        env=settings.app_env,
        use_webhook=settings.use_webhook,
        webhook_url=settings.webhook_url,
        deploy_commit_short=deploy_commit_short,
    )

    if settings.use_webhook:
        await run_webhook_mode()
    else:
        await run_polling_mode()


if __name__ == "__main__":
    asyncio.run(main())
