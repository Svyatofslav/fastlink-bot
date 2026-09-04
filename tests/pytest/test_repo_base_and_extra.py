from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from database.enums import SubscriptionStatus
from database.repo.subscriptions import SubscriptionRepo
from database.repo.tariffs import TariffRepo
from database.repo.users import UserRepo
from tests.pytest.factories import (
    make_server,
    make_subscription,
    make_tariff,
    make_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# BaseRepo.delete / get_all — через UserRepo как конкретную реализацию
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_repo_delete_removes_row(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    user = make_user()
    db_session.add(user)
    await db_session.flush()
    user_id = user.id

    await repo.delete(user)
    await db_session.flush()

    assert await repo.get_by_id(user_id) is None


@pytest.mark.asyncio
async def test_base_repo_get_all_returns_all_rows(db_session: AsyncSession) -> None:
    repo = UserRepo(db_session)
    user1 = make_user()
    user2 = make_user()
    db_session.add_all([user1, user2])
    await db_session.flush()

    all_users = await repo.get_all()
    ids = {u.id for u in all_users}

    assert user1.id in ids
    assert user2.id in ids


# ---------------------------------------------------------------------------
# SubscriptionRepo.get_active_by_user / get_by_marzban_username
# ---------------------------------------------------------------------------


async def _make_subscription_with_status(
    db_session: AsyncSession, *, suffix: str, status: SubscriptionStatus
):
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()
    sub = make_subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username=f"mz-{suffix}",
        status=status,
    )
    db_session.add(sub)
    await db_session.flush()
    return user, server, sub


@pytest.mark.asyncio
async def test_get_active_by_user_excludes_disabled(db_session: AsyncSession) -> None:
    user, _server, active_sub = await _make_subscription_with_status(
        db_session, suffix="active1", status=SubscriptionStatus.ACTIVE
    )
    server2 = make_server()
    db_session.add(server2)
    await db_session.flush()
    tariff2 = make_tariff(server_id=server2.id)
    db_session.add(tariff2)
    await db_session.flush()
    disabled_sub = make_subscription(
        user_id=user.id,
        server_id=server2.id,
        tariff_id=tariff2.id,
        marzban_username="mz-disabled1",
        status=SubscriptionStatus.DISABLED,
    )
    db_session.add(disabled_sub)
    await db_session.flush()

    repo = SubscriptionRepo(db_session)
    result = await repo.get_active_by_user(user.id)
    ids = {s.id for s in result}

    assert active_sub.id in ids
    assert disabled_sub.id not in ids


@pytest.mark.asyncio
async def test_get_by_marzban_username_found(db_session: AsyncSession) -> None:
    _user, server, sub = await _make_subscription_with_status(
        db_session, suffix="findme", status=SubscriptionStatus.ACTIVE
    )

    repo = SubscriptionRepo(db_session)
    result = await repo.get_by_marzban_username(server.id, "mz-findme")

    assert result is not None
    assert result.id == sub.id


@pytest.mark.asyncio
async def test_get_by_marzban_username_wrong_server_returns_none(
    db_session: AsyncSession,
) -> None:
    _user, _server, _sub = await _make_subscription_with_status(
        db_session, suffix="wrongsrv", status=SubscriptionStatus.ACTIVE
    )

    repo = SubscriptionRepo(db_session)
    result = await repo.get_by_marzban_username(999999, "mz-wrongsrv")

    assert result is None


# ---------------------------------------------------------------------------
# TariffRepo.get_active / set_active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tariff_get_active_excludes_inactive(db_session: AsyncSession) -> None:
    server = make_server()
    db_session.add(server)
    await db_session.flush()
    active_tariff = make_tariff(server_id=server.id, is_active=True)
    inactive_tariff = make_tariff(server_id=server.id, is_active=False)
    db_session.add_all([active_tariff, inactive_tariff])
    await db_session.flush()

    repo = TariffRepo(db_session)
    result = await repo.get_active()
    ids = {t.id for t in result}

    assert active_tariff.id in ids
    assert inactive_tariff.id not in ids


@pytest.mark.asyncio
async def test_tariff_set_active_toggles_flag(db_session: AsyncSession) -> None:
    server = make_server()
    db_session.add(server)
    await db_session.flush()
    tariff = make_tariff(server_id=server.id, is_active=True)
    db_session.add(tariff)
    await db_session.flush()

    repo = TariffRepo(db_session)
    updated = await repo.set_active(tariff, active=False)

    assert updated.is_active is False
