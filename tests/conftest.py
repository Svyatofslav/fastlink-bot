from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_test_session_factory


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    factory = get_test_session_factory()
    async with factory() as session:
        yield session
        await session.close()
