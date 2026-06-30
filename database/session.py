from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.engine import create_engine, create_test_engine

# Ленивая инициализация фабрик сессий, чтобы не дёргать Settings() при импорте.
_async_session_factory: async_sessionmaker[AsyncSession] | None = None
_test_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        engine = create_engine()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


def _get_test_session_factory() -> async_sessionmaker[AsyncSession]:
    global _test_session_factory
    if _test_session_factory is None:
        engine = create_test_engine()
        _test_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _test_session_factory


# Сохраняем старые имена для совместимости с существующим кодом.
AsyncSessionFactory = _get_async_session_factory()
TestSessionFactory = _get_test_session_factory()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session
