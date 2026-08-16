from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.engine import create_engine, create_test_engine


class _SessionFactoryCache:
    """
    Ленивый контейнер для singleton-фабрик сессий.

    Инкапсулирует mutable state вместо module-level global переменных —
    это позволяет избежать PLW0603, сохранив ровно то же поведение:
    фабрика создаётся один раз при первом вызове и переиспользуется
    при всех последующих (в т.ч. если pool_size передан другим).
    """

    def __init__(self) -> None:
        self.async_factory: async_sessionmaker[AsyncSession] | None = None
        self.test_factory: async_sessionmaker[AsyncSession] | None = None


_cache = _SessionFactoryCache()


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    if _cache.async_factory is None:
        engine = create_engine()
        _cache.async_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _cache.async_factory


def get_test_session_factory(pool_size: int = 1) -> async_sessionmaker[AsyncSession]:
    if _cache.test_factory is None:
        engine = create_test_engine(pool_size=pool_size)
        _cache.test_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _cache.test_factory


async def get_session() -> AsyncGenerator[AsyncSession]:
    async_session_factory = get_async_session_factory()
    async with async_session_factory() as session:
        yield session
