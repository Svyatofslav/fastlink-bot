from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from settings_schema import Settings


@dataclass(frozen=True)
class AdminSession:
    admin_id: int
    telegram_id: int


class AdminSessionStore:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._ttl_seconds = settings.admin_session_ttl_seconds

    def _key(self, telegram_id: int) -> str:
        return f"admin_session:{telegram_id}"

    async def create_session(self, admin_id: int, telegram_id: int) -> None:
        # Храним простую строку вида "admin_id:telegram_id".
        value = f"{admin_id}:{telegram_id}"
        await self._redis.set(self._key(telegram_id), value, ex=self._ttl_seconds)

    async def get_session(self, telegram_id: int) -> AdminSession | None:
        value = await self._redis.get(self._key(telegram_id))
        if value is None:
            return None

        try:
            admin_id_str, telegram_id_str = value.decode("utf-8").split(":", 1)
            admin_id = int(admin_id_str)
            tg_id = int(telegram_id_str)
        except Exception:
            return None

        return AdminSession(admin_id=admin_id, telegram_id=tg_id)

    async def destroy_session(self, telegram_id: int) -> None:
        await self._redis.delete(self._key(telegram_id))
