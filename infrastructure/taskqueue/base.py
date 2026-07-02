from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from infrastructure.taskqueue.types import LockHandle


class TaskQueue(ABC):
    """
    Абстракция над очередью фоновых задач.

    Реализация (ARQ, RQ, Celery и т.д.) должна жить только в конкретном
    *_impl.py модуле. Остальной код проекта обязан зависеть только от
    этого интерфейса, а не от конкретного backend'а.
    """

    @abstractmethod
    async def enqueue(
        self,
        function_name: str,
        *args: Any,
        job_id: str | None = None,
        defer_by_seconds: int | None = None,
        **kwargs: Any,
    ) -> str | None:
        """
        Ставит задачу в очередь.

        :param function_name: имя зарегистрированной функции-задачи.
        :param job_id: если задан — используется для идемпотентности
            (повторная постановка с тем же job_id будет проигнорирована
            backend'ом, пока предыдущая задача не завершится/не истечёт).
        :param defer_by_seconds: отложить выполнение на N секунд.
        :return: идентификатор задачи или None, если backend решил,
            что задача уже поставлена (дедупликация по job_id).
        """
        raise NotImplementedError

    @abstractmethod
    async def acquire_lock(
        self,
        key: str,
        *,
        ttl_seconds: int = 60,
    ) -> LockHandle | None:
        """
        Пытается атомарно захватить именованную распределённую блокировку.

        :param key: логическое имя ресурса, который блокируем.
        :param ttl_seconds: время жизни блокировки на случай, если
            держатель упадёт и не снимет её сам.
        :return: LockHandle, если блокировка захвачена, иначе None.
        """
        raise NotImplementedError

    @asynccontextmanager
    async def lock(
        self,
        key: str,
        *,
        ttl_seconds: int = 60,
    ) -> AsyncIterator[bool]:
        """
        Удобный контекст-менеджер поверх acquire_lock.

        Использование:
            async with task_queue.lock("subscriptions:sync") as acquired:
                if not acquired:
                    return
                ...
        """
        handle = await self.acquire_lock(key, ttl_seconds=ttl_seconds)
        try:
            yield handle is not None
        finally:
            if handle is not None:
                await handle.release()

    @abstractmethod
    async def close(self) -> None:
        """Закрывает соединения backend'а. Вызывать при graceful shutdown."""
        raise NotImplementedError
