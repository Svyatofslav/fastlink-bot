from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LockHandle(Protocol):
    """Хэндл распределённой блокировки, не привязанный к конкретному backend."""

    @property
    def acquired(self) -> bool:
        """True, если блокировка была успешно захвачена и ещё не снята."""
        ...

    async def release(self) -> None:
        """Снимает блокировку, если она принадлежит этому хэндлу."""
        ...


class TaskEnqueueError(Exception):
    """Ошибка постановки задачи в очередь."""


class TaskQueueConnectionError(Exception):
    """Ошибка соединения с backend очереди задач."""
