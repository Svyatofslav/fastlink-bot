from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import TestSessionFactory


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with TestSessionFactory() as session:
        yield session
        await session.close()
