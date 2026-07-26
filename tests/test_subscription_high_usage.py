from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import SubscriptionStatus
from database.models import Server, Subscription, Tariff, User
from database.repo.subscriptions import SubscriptionRepo


async def _make_base(db_session: AsyncSession, suffix: str):
    user = User(telegram_id=500_000_000 + abs(hash(suffix)) % 90_000_000)
    server = Server(
        name=f"usage-server-{suffix}",
        inbound_tag=f"usage-inbound-{suffix}",
    )
    tariff = Tariff(
        server_id=None,
        name=f"Usage tariff {suffix}",
        duration_days=30,
        data_limit_bytes=1_000_000,
        price_amount=10000,
    )
    db_session.add_all([user, server, tariff])
    await db_session.flush()
    return user, server, tariff


async def _make_sub(
    db_session,
    user,
    server,
    tariff,
    username,
    *,
    data_limit_bytes,
    data_used_bytes,
    status=SubscriptionStatus.ACTIVE,
):
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username=username,
        status=status,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
        data_limit_bytes=data_limit_bytes,
        data_used_bytes=data_used_bytes,
        auto_renew=False,
        subscription_url=f"https://example.com/sub/{username}",
    )
    db_session.add(sub)
    await db_session.flush()
    return sub


@pytest.mark.asyncio
async def test_get_high_usage_boundary_exactly_at_threshold_included(
    db_session: AsyncSession,
) -> None:
    """
    get_high_usage использует data_used_bytes * 100 / data_limit_bytes >= threshold_percent.
    Подписка РОВНО на пороге (80%) должна быть включена (>=), а на 1 байт
    меньше порога — не должна.
    """
    repo = SubscriptionRepo(db_session)
    user, server, tariff = await _make_base(db_session, "exact80")

    data_limit = 1_000_000
    exactly_80 = await _make_sub(
        db_session,
        user,
        server,
        tariff,
        "exact-80",
        data_limit_bytes=data_limit,
        data_used_bytes=800_000,
    )
    just_below_80 = await _make_sub(
        db_session,
        user,
        server,
        tariff,
        "below-80",
        data_limit_bytes=data_limit,
        data_used_bytes=799_999,
    )
    await db_session.commit()

    result = await repo.get_high_usage(threshold_percent=80)
    ids = {s.id for s in result}

    assert exactly_80.id in ids, "usage == 80% должен включаться (>=)"
    assert just_below_80.id not in ids, "usage чуть ниже 80% не должен включаться"


@pytest.mark.asyncio
async def test_get_high_usage_excludes_zero_data_limit(
    db_session: AsyncSession,
) -> None:
    """
    Подписки с data_limit_bytes == 0 (безлимит) должны быть полностью
    исключены из get_high_usage независимо от data_used_bytes, иначе
    деление на ноль сломает SQL-запрос.
    """
    repo = SubscriptionRepo(db_session)
    user, server, tariff = await _make_base(db_session, "unlimited")

    unlimited_sub = await _make_sub(
        db_session,
        user,
        server,
        tariff,
        "unlimited-heavy",
        data_limit_bytes=0,
        data_used_bytes=999_999_999,
    )
    await db_session.commit()

    result = await repo.get_high_usage(threshold_percent=1)
    ids = {s.id for s in result}

    assert unlimited_sub.id not in ids, (
        "data_limit_bytes == 0 не должен вызывать деление на 0 и не "
        "должен попадать в high-usage выборку"
    )


@pytest.mark.asyncio
async def test_get_high_usage_excludes_non_active_status(
    db_session: AsyncSession,
) -> None:
    """
    get_high_usage должен учитывать только ACTIVE подписки, даже если
    usage% формально превышает порог у DISABLED подписки.
    """
    repo = SubscriptionRepo(db_session)
    user, server, tariff = await _make_base(db_session, "disabled")

    disabled_sub = await _make_sub(
        db_session,
        user,
        server,
        tariff,
        "disabled-high-usage",
        data_limit_bytes=1_000_000,
        data_used_bytes=999_999,
        status=SubscriptionStatus.DISABLED,
    )
    await db_session.commit()

    result = await repo.get_high_usage(threshold_percent=50)
    ids = {s.id for s in result}

    assert disabled_sub.id not in ids
