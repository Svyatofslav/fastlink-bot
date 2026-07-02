from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from config import settings
from infrastructure.taskqueue.base import TaskQueue
from infrastructure.taskqueue.types import (
    LockHandle,
    TaskEnqueueError,
    TaskQueueConnectionError,
)

logger = structlog.get_logger(__name__)

# Снимаем лок только если он всё ещё принадлежит нам (по токену),
# иначе можно случайно удалить чужую блокировку, захваченную после
# истечения TTL нашей.
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_LOCK_KEY_PREFIX = "taskqueue:lock:"


def build_redis_settings() -> RedisSettings:
    """Единая точка сборки RedisSettings для ARQ (worker + enqueue side)."""
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        database=settings.redis_taskqueue_db,
    )


@dataclass
class _ArqLockHandle:
    _redis: ArqRedis
    _key: str
    _token: str
    _acquired: bool = field(default=True, repr=False)

    @property
    def acquired(self) -> bool:
        return self._acquired

    async def release(self) -> None:
        if not self._acquired:
            return
        try:
            await self._redis.eval(_RELEASE_LOCK_SCRIPT, 1, self._key, self._token)
        finally:
            # Помечаем как снятый в любом случае, чтобы не пытаться
            # снять его повторно (например, в finally вызывающего кода).
            self._acquired = False


class ArqTaskQueue(TaskQueue):
    """ARQ-реализация TaskQueue поверх redis.asyncio через arq.ArqRedis."""

    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    @classmethod
    async def create(
        cls, redis_settings: RedisSettings | None = None
    ) -> "ArqTaskQueue":
        try:
            redis = await create_pool(redis_settings or build_redis_settings())
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueConnectionError(
                f"Failed to connect to Redis for ARQ: {exc}"
            ) from exc
        return cls(redis)

    async def enqueue(
        self,
        function_name: str,
        *args: Any,
        job_id: str | None = None,
        defer_by_seconds: int | None = None,
        **kwargs: Any,
    ) -> str | None:
        try:
            job = await self._redis.enqueue_job(
                function_name,
                *args,
                _job_id=job_id,
                _defer_by=defer_by_seconds,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise TaskEnqueueError(
                f"Failed to enqueue task '{function_name}': {exc}"
            ) from exc

        if job is None:
            logger.info(
                "taskqueue_enqueue_deduped",
                function_name=function_name,
                job_id=job_id,
            )
            return None

        logger.info(
            "taskqueue_enqueued",
            function_name=function_name,
            job_id=job.job_id,
        )
        return job.job_id

    async def acquire_lock(
        self,
        key: str,
        *,
        ttl_seconds: int = 60,
    ) -> LockHandle | None:
        token = uuid.uuid4().hex
        lock_key = f"{_LOCK_KEY_PREFIX}{key}"

        acquired = await self._redis.set(
            lock_key,
            token,
            nx=True,
            ex=ttl_seconds,
        )
        if not acquired:
            logger.debug("taskqueue_lock_busy", key=key)
            return None

        logger.debug("taskqueue_lock_acquired", key=key, ttl_seconds=ttl_seconds)
        return _ArqLockHandle(_redis=self._redis, _key=lock_key, _token=token)

    async def close(self) -> None:
        await self._redis.close()
