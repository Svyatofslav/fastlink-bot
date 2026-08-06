from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import Base
from database.engine import create_test_engine


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_test_engine()

    async with engine.connect() as conn:
        await conn.begin()
        nested = await conn.begin_nested()  # SAVEPOINT

        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

        yield session

        await session.close()
        if nested.is_active:
            await nested.rollback()
        await conn.rollback()

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_committed_data():
    """
    Гарантированная очистка тестовой БД после КАЖДОГО теста.

    db_session (выше) сам защищён через SAVEPOINT + rollback и ничего
    не оставляет за собой. Но race-тесты (concurrent_session_factory)
    обязаны делать реальный commit, чтобы проверить гонку — и без этой
    fixture их данные оставались бы в общей тестовой БД до конца всей
    pytest-сессии, тихо влияя на list_pending/SELECT в других тестах
    (как уже произошло: RECEIVED-событие из test_webhook_event_race.py
    подхватилось в test_webhook_processing_race.py).

    TRUNCATE ... CASCADE после каждого теста — универсальная защита,
    не требующая от каждого нового race-теста самостоятельно помнить
    про фильтрацию по своему id/external_id.
    """
    yield

    engine = create_test_engine()
    async with engine.connect() as conn:
        table_names = [t.name for t in Base.metadata.sorted_tables]
        if table_names:
            tables_sql = ", ".join(f'"{name}"' for name in table_names)
            await conn.execute(
                text(f"TRUNCATE TABLE {tables_sql} RESTART IDENTITY CASCADE")
            )
            await conn.commit()
    await engine.dispose()
