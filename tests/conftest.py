from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

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
