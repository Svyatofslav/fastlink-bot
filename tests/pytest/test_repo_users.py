from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy.exc import IntegrityError

from database.repo.users import UserRepo
from tests.pytest.factories import make_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def make_tg_user(
    *,
    tg_id: int = 900_000_001,
    username: str | None = "tguser",
    first_name: str = "Test",
    last_name: str | None = "User",
    language_code: str | None = "ru",
) -> TelegramUser:
    return TelegramUser(
        id=tg_id,
        is_bot=False,
        first_name=first_name,
        last_name=last_name,
        username=username,
        language_code=language_code,
    )


# ---------------------------------------------------------------------------
# get_by_telegram_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_telegram_id_found(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    user = make_user(telegram_id=900_000_010)
    db_session.add(user)
    await db_session.flush()

    result = await repo.get_by_telegram_id(900_000_010)

    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_get_by_telegram_id_not_found(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)

    result = await repo.get_by_telegram_id(900_000_099)

    assert result is None


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_creates_new_user(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    tg_user = make_tg_user(tg_id=900_000_020)

    user, is_new = await repo.get_or_create(tg_user)

    assert is_new is True
    assert user.telegram_id == 900_000_020
    assert user.username == "tguser"
    assert user.language_code == "ru"


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_without_creating(
    db_session: AsyncSession,
) -> None:
    repo = UserRepo(db_session)
    existing = make_user(telegram_id=900_000_021)
    db_session.add(existing)
    await db_session.flush()

    tg_user = make_tg_user(tg_id=900_000_021)
    user, is_new = await repo.get_or_create(tg_user)

    assert is_new is False
    assert user.id == existing.id


@pytest.mark.asyncio
async def test_get_or_create_no_language_code_defaults_to_ru(
    db_session: AsyncSession,
) -> None:
    repo = UserRepo(db_session)
    tg_user = make_tg_user(tg_id=900_000_022, language_code=None)

    user, is_new = await repo.get_or_create(tg_user)

    assert is_new is True
    assert user.language_code == "ru"


@pytest.mark.asyncio
async def test_get_or_create_race_resolves_to_existing(
    db_session: AsyncSession,
) -> None:
    repo = UserRepo(db_session)
    tg_user = make_tg_user(tg_id=900_000_023)
    existing_after_race = make_user(telegram_id=900_000_023)

    with (
        patch.object(
            repo,
            "get_by_telegram_id",
            new=AsyncMock(side_effect=[None, existing_after_race]),
        ),
        patch.object(
            repo, "create", new=AsyncMock(side_effect=IntegrityError("dup", None, None))
        ),
    ):
        user, is_new = await repo.get_or_create(tg_user)

    assert is_new is False
    assert user is existing_after_race


@pytest.mark.asyncio
async def test_get_or_create_race_unresolved_reraises(
    db_session: AsyncSession,
) -> None:
    repo = UserRepo(db_session)
    tg_user = make_tg_user(tg_id=900_000_024)

    with (
        patch.object(
            repo, "get_by_telegram_id", new=AsyncMock(side_effect=[None, None])
        ),
        patch.object(
            repo, "create", new=AsyncMock(side_effect=IntegrityError("dup", None, None))
        ),
        pytest.raises(IntegrityError),
    ):
        await repo.get_or_create(tg_user)


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_profile_no_changes_returns_same_user(
    db_session: AsyncSession,
) -> None:
    repo = UserRepo(db_session)
    user = make_user(username="same", first_name="Same", last_name="User")
    db_session.add(user)
    await db_session.flush()

    tg_user = make_tg_user(username="same", first_name="Same", last_name="User")

    result = await repo.update_profile(user, tg_user)

    assert result is user


@pytest.mark.asyncio
async def test_update_profile_username_changed(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    user = make_user(username="old", first_name="Same", last_name="User")
    db_session.add(user)
    await db_session.flush()

    tg_user = make_tg_user(username="new", first_name="Same", last_name="User")

    result = await repo.update_profile(user, tg_user)

    assert result.username == "new"
    assert result.first_name == "Same"


@pytest.mark.asyncio
async def test_update_profile_all_fields_changed(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    user = make_user(username="old", first_name="Old", last_name="Name")
    db_session.add(user)
    await db_session.flush()

    tg_user = make_tg_user(username="new", first_name="New", last_name="Surname")

    result = await repo.update_profile(user, tg_user)

    assert result.username == "new"
    assert result.first_name == "New"
    assert result.last_name == "Surname"


# ---------------------------------------------------------------------------
# set_last_active / set_banned / get_all_active / set_last_active_message_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_last_active_updates_timestamp(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    user = make_user(last_active_at=None)
    db_session.add(user)
    await db_session.flush()

    await repo.set_last_active(user)

    assert user.last_active_at is not None


@pytest.mark.asyncio
async def test_set_banned_true_and_false(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    user = make_user(is_banned=False)
    db_session.add(user)
    await db_session.flush()

    banned = await repo.set_banned(user, banned=True)
    assert banned.is_banned is True

    unbanned = await repo.set_banned(user, banned=False)
    assert unbanned.is_banned is False


@pytest.mark.asyncio
async def test_get_all_active_excludes_inactive_and_banned(
    db_session: AsyncSession,
) -> None:
    repo = UserRepo(db_session)
    active_user = make_user(is_active=True, is_banned=False)
    inactive_user = make_user(is_active=False, is_banned=False)
    banned_user = make_user(is_active=True, is_banned=True)
    db_session.add_all([active_user, inactive_user, banned_user])
    await db_session.flush()

    result = await repo.get_all_active()
    ids = {u.id for u in result}

    assert active_user.id in ids
    assert inactive_user.id not in ids
    assert banned_user.id not in ids


@pytest.mark.asyncio
async def test_set_last_active_message_id_updates_field(
    db_session: AsyncSession,
) -> None:
    repo = UserRepo(db_session)
    user = make_user(last_active_message_id=None)
    db_session.add(user)
    await db_session.flush()

    updated = await repo.set_last_active_message_id(user, 12345)

    assert updated.last_active_message_id == 12345
