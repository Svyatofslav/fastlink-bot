from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from middlewares import (
    AdminSessionMiddleware,
    DbSessionMiddleware,
    LoggingMiddleware,
    ThrottlingMiddleware,
    UserMiddleware,
)

# ---------------------------------------------------------------------------
# DbSessionMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_session_middleware_injects_session_and_commits():
    fake_session = AsyncMock()
    session_factory = MagicMock(return_value=fake_session)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    middleware = DbSessionMiddleware(session_factory=session_factory)
    handler = AsyncMock(return_value="ok")
    data: dict = {}

    result = await middleware(handler, MagicMock(spec=Message), data)

    assert result == "ok"
    assert data["session"] is fake_session
    handler.assert_awaited_once()
    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_db_session_middleware_rolls_back_on_exception():
    fake_session = AsyncMock()
    session_factory = MagicMock(return_value=fake_session)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    middleware = DbSessionMiddleware(session_factory=session_factory)
    handler = AsyncMock(side_effect=ValueError("boom"))

    with pytest.raises(ValueError, match="boom"):
        await middleware(handler, MagicMock(spec=Message), {})

    fake_session.rollback.assert_awaited_once()
    fake_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# ThrottlingMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttling_middleware_blocks_when_already_throttled():
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value="1")

    middleware = ThrottlingMiddleware(redis=fake_redis)
    handler = AsyncMock(return_value="ok")
    user = MagicMock(telegram_id=123)
    event = MagicMock(spec=Message)

    result = await middleware(handler, event, {"user": user})

    assert result is None
    handler.assert_not_awaited()
    fake_redis.get.assert_awaited_once_with("throttle:123")
    fake_redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_throttling_middleware_allows_when_not_throttled():
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.set = AsyncMock(return_value=True)

    middleware = ThrottlingMiddleware(redis=fake_redis)
    handler = AsyncMock(return_value="ok")
    user = MagicMock(telegram_id=456)
    event = MagicMock(spec=CallbackQuery)

    result = await middleware(handler, event, {"user": user})

    assert result == "ok"
    handler.assert_awaited_once()
    fake_redis.set.assert_awaited_once()
    _, kwargs = fake_redis.set.call_args
    assert kwargs.get("nx") is True


@pytest.mark.asyncio
async def test_throttling_middleware_skips_when_no_user_in_data():
    fake_redis = AsyncMock()
    middleware = ThrottlingMiddleware(redis=fake_redis)
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message)

    result = await middleware(handler, event, {})

    assert result == "ok"
    handler.assert_awaited_once()
    fake_redis.get.assert_not_called()


@pytest.mark.asyncio
async def test_throttling_middleware_passes_through_non_message_callback_events():
    fake_redis = AsyncMock()
    middleware = ThrottlingMiddleware(redis=fake_redis)
    handler = AsyncMock(return_value="ok")
    event = MagicMock()  # без spec -> не Message и не CallbackQuery

    result = await middleware(handler, event, {"user": MagicMock(telegram_id=1)})

    assert result == "ok"
    handler.assert_awaited_once()
    fake_redis.get.assert_not_called()


@pytest.mark.asyncio
async def test_throttling_middleware_different_users_not_blocking_each_other():
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.set = AsyncMock(return_value=True)

    middleware = ThrottlingMiddleware(redis=fake_redis)
    handler = AsyncMock(return_value="ok")

    user_a = MagicMock(telegram_id=111)
    user_b = MagicMock(telegram_id=222)
    event = MagicMock(spec=Message)

    await middleware(handler, event, {"user": user_a})
    await middleware(handler, event, {"user": user_b})

    assert handler.await_count == 2
    called_keys = [call.args[0] for call in fake_redis.get.call_args_list]
    assert "throttle:111" in called_keys
    assert "throttle:222" in called_keys


# ---------------------------------------------------------------------------
# UserMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_middleware_creates_new_user_and_injects_into_data(monkeypatch):
    fake_repo = AsyncMock()
    fake_user = MagicMock(is_banned=False)
    fake_repo.get_or_create = AsyncMock(return_value=(fake_user, True))
    fake_repo.set_last_active = AsyncMock()
    monkeypatch.setattr("middlewares.user.UserRepo", lambda session: fake_repo)

    middleware = UserMiddleware()
    handler = AsyncMock(return_value="ok")
    tg_user = MagicMock(is_bot=False)
    event = MagicMock(spec=Message, from_user=tg_user)
    data = {"session": MagicMock()}

    result = await middleware(handler, event, data)

    assert result == "ok"
    assert data["user"] is fake_user
    assert data["user_created"] is True
    fake_repo.get_or_create.assert_awaited_once_with(tg_user)
    fake_repo.update_profile.assert_not_called()
    fake_repo.set_last_active.assert_awaited_once_with(fake_user)
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_middleware_updates_existing_user_profile(monkeypatch):
    fake_repo = AsyncMock()
    existing_user = MagicMock(is_banned=False)
    updated_user = MagicMock(is_banned=False)
    fake_repo.get_or_create = AsyncMock(return_value=(existing_user, False))
    fake_repo.update_profile = AsyncMock(return_value=updated_user)
    fake_repo.set_last_active = AsyncMock()
    monkeypatch.setattr("middlewares.user.UserRepo", lambda session: fake_repo)

    middleware = UserMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=MagicMock(is_bot=False))
    data = {"session": MagicMock()}

    await middleware(handler, event, data)

    fake_repo.update_profile.assert_awaited_once()
    fake_repo.set_last_active.assert_awaited_once_with(updated_user)
    assert data["user"] is updated_user
    assert data["user_created"] is False


@pytest.mark.asyncio
async def test_user_middleware_blocks_banned_user(monkeypatch):
    fake_repo = AsyncMock()
    banned_user = MagicMock(is_banned=True)
    fake_repo.get_or_create = AsyncMock(return_value=(banned_user, False))
    fake_repo.update_profile = AsyncMock(return_value=banned_user)
    fake_repo.set_last_active = AsyncMock()
    monkeypatch.setattr("middlewares.user.UserRepo", lambda session: fake_repo)

    middleware = UserMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=MagicMock(is_bot=False))
    data = {"session": MagicMock()}

    result = await middleware(handler, event, data)

    assert result is None
    handler.assert_not_awaited()
    fake_repo.set_last_active.assert_not_called()
    assert "user" not in data


@pytest.mark.asyncio
async def test_user_middleware_skips_bot_users():
    middleware = UserMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=MagicMock(is_bot=True))

    result = await middleware(handler, event, {"session": MagicMock()})

    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_middleware_skips_when_no_from_user():
    middleware = UserMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=None)

    result = await middleware(handler, event, {"session": MagicMock()})

    assert result == "ok"
    handler.assert_awaited_once()


# ---------------------------------------------------------------------------
# AdminSessionMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_session_middleware_injects_session_when_found(monkeypatch):
    fake_store = AsyncMock()
    fake_session = MagicMock()
    fake_store.get_session = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(
        "middlewares.admin_session.AdminSessionStore",
        lambda redis, settings: fake_store,
    )

    middleware = AdminSessionMiddleware(redis=MagicMock(), settings=MagicMock())
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=MagicMock(id=777))
    data: dict = {}

    result = await middleware(handler, event, data)

    assert result == "ok"
    assert data["admin_session"] is fake_session
    fake_store.get_session.assert_awaited_once_with(777)


@pytest.mark.asyncio
async def test_admin_session_middleware_skips_when_no_session_found(monkeypatch):
    fake_store = AsyncMock()
    fake_store.get_session = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "middlewares.admin_session.AdminSessionStore",
        lambda redis, settings: fake_store,
    )

    middleware = AdminSessionMiddleware(redis=MagicMock(), settings=MagicMock())
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=MagicMock(id=777))
    data: dict = {}

    result = await middleware(handler, event, data)

    assert "admin_session" not in data
    assert result == "ok"


@pytest.mark.asyncio
async def test_admin_session_middleware_skips_when_no_from_user(monkeypatch):
    fake_store = AsyncMock()
    monkeypatch.setattr(
        "middlewares.admin_session.AdminSessionStore",
        lambda redis, settings: fake_store,
    )

    middleware = AdminSessionMiddleware(redis=MagicMock(), settings=MagicMock())
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=None)

    result = await middleware(handler, event, {})

    fake_store.get_session.assert_not_called()
    assert result == "ok"


@pytest.mark.asyncio
async def test_admin_session_middleware_works_for_callback_query(monkeypatch):
    fake_store = AsyncMock()
    fake_session = MagicMock()
    fake_store.get_session = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(
        "middlewares.admin_session.AdminSessionStore",
        lambda redis, settings: fake_store,
    )

    middleware = AdminSessionMiddleware(redis=MagicMock(), settings=MagicMock())
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=CallbackQuery, from_user=MagicMock(id=999))
    data: dict = {}

    result = await middleware(handler, event, data)

    assert data["admin_session"] is fake_session
    assert result == "ok"


# ---------------------------------------------------------------------------
# LoggingMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logging_middleware_returns_handler_result():
    middleware = LoggingMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=MagicMock(id=1), text="hi", caption=None)

    result = await middleware(handler, event, {})

    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_logging_middleware_reraises_exception_from_handler():
    middleware = LoggingMiddleware()
    handler = AsyncMock(side_effect=ValueError("boom"))
    event = MagicMock(spec=Message, from_user=MagicMock(id=1), text="hi", caption=None)

    with pytest.raises(ValueError, match="boom"):
        await middleware(handler, event, {})


@pytest.mark.asyncio
async def test_logging_middleware_handles_event_without_from_user():
    middleware = LoggingMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock(spec=Message, from_user=None, text="hi", caption=None)

    result = await middleware(handler, event, {})

    assert result == "ok"
    handler.assert_awaited_once()
