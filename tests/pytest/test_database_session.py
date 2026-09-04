from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database.session as session_module


@pytest.fixture(autouse=True)
def _reset_session_cache():
    """Каждый тест получает свежий _SessionFactoryCache, чтобы не течь
    состояние (закэшированную фабрику) между тестами и не трогать
    реальный create_engine()/create_test_engine()."""
    original_cache = session_module._cache
    session_module._cache = session_module._SessionFactoryCache()
    yield
    session_module._cache = original_cache


def test_get_async_session_factory_creates_once_and_caches() -> None:
    fake_engine = MagicMock()
    with patch.object(
        session_module, "create_engine", return_value=fake_engine
    ) as create_engine_mock:
        factory1 = session_module.get_async_session_factory()
        factory2 = session_module.get_async_session_factory()

    create_engine_mock.assert_called_once()
    assert factory1 is factory2


def test_get_test_session_factory_creates_once_and_caches() -> None:
    fake_engine = MagicMock()
    with patch.object(
        session_module, "create_test_engine", return_value=fake_engine
    ) as create_test_engine_mock:
        factory1 = session_module.get_test_session_factory(pool_size=3)
        factory2 = session_module.get_test_session_factory(pool_size=7)

    create_test_engine_mock.assert_called_once_with(pool_size=3)
    assert factory1 is factory2


@pytest.mark.asyncio
async def test_get_session_yields_and_closes_session() -> None:
    fake_session = AsyncMock()

    class _FakeSessionCM:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, *exc):
            return False

    fake_factory = MagicMock(return_value=_FakeSessionCM())

    with patch.object(
        session_module, "get_async_session_factory", return_value=fake_factory
    ):
        gen = session_module.get_session()
        session = await gen.__anext__()
        assert session is fake_session

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
