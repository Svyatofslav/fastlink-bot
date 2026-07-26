from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import SubscriptionStatus
from database.models import Server, Subscription, Tariff, User
from database.repo.subscriptions import SubscriptionRepo
import database.repo.subscriptions as subscriptions_module


class _FrozenDatetime(datetime):
    _frozen_now: datetime

    @classmethod
    def now(cls, tz=None):
        return cls._frozen_now


async def _make_base_entities(db_session: AsyncSession, suffix: str):
    user = User(telegram_id=hash(suffix) % 1_000_000_000 + 400_000_000)
    server = Server(
        name=f"boundary-server-{suffix}",
        inbound_tag=f"boundary-inbound-{suffix}",
    )
    tariff = Tariff(
        server_id=None,
        name=f"Boundary tariff {suffix}",
        duration_days=30,
        data_limit_bytes=10_000_000,
        price_amount=10000,
    )
    db_session.add_all([user, server, tariff])
    await db_session.flush()
    return user, server, tariff


async def _make_subscription(
    db_session, user, server, tariff, marzban_username, expires_at
):
    sub = Subscription(
        user_id=user.id,
        server_id=server.id,
        tariff_id=tariff.id,
        marzban_username=marzban_username,
        status=SubscriptionStatus.ACTIVE,
        starts_at=expires_at - timedelta(days=30),
        expires_at=expires_at,
        data_limit_bytes=10_000_000,
        data_used_bytes=0,
        auto_renew=False,
        subscription_url=f"https://example.com/sub/{marzban_username}",
    )
    db_session.add(sub)
    await db_session.flush()
    return sub


@pytest.mark.asyncio
async def test_get_expired_boundary_exactly_now_is_included(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    get_expired использует expires_at <= now — подписка, у которой
    expires_at РОВНО равен now(), должна считаться просроченной и
    попадать в выборку (граница включительна).
    """
    frozen_now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    _FrozenDatetime._frozen_now = frozen_now
    monkeypatch.setattr(subscriptions_module, "datetime", _FrozenDatetime)

    repo = SubscriptionRepo(db_session)
    user, server, tariff = await _make_base_entities(db_session, "exp-eq")

    exact_boundary_sub = await _make_subscription(
        db_session, user, server, tariff, "exact-boundary", frozen_now
    )
    one_microsecond_future_sub = await _make_subscription(
        db_session,
        user,
        server,
        tariff,
        "one-us-future",
        frozen_now + timedelta(microseconds=1),
    )
    await db_session.commit()

    expired_list = await repo.get_expired()
    ids = {s.id for s in expired_list}

    assert exact_boundary_sub.id in ids, (
        "expires_at == now должен считаться просроченным согласно "
        "условию expires_at <= now в get_expired."
    )
    assert one_microsecond_future_sub.id not in ids, (
        "expires_at на 1 микросекунду позже now не должен считаться просроченным."
    )


@pytest.mark.asyncio
async def test_get_expiring_boundary_exactly_now_is_excluded(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    get_expiring использует expires_at > now (строгое неравенство) —
    подписка с expires_at РОВНО now должна считаться уже просроченной
    и НЕ попадать в окно "скоро истекающих".
    """
    frozen_now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    _FrozenDatetime._frozen_now = frozen_now
    monkeypatch.setattr(subscriptions_module, "datetime", _FrozenDatetime)

    repo = SubscriptionRepo(db_session)
    user, server, tariff = await _make_base_entities(db_session, "win-lo")

    exactly_now_sub = await _make_subscription(
        db_session, user, server, tariff, "exactly-now", frozen_now
    )
    just_after_now_sub = await _make_subscription(
        db_session,
        user,
        server,
        tariff,
        "just-after-now",
        frozen_now + timedelta(microseconds=1),
    )
    await db_session.commit()

    expiring_list = await repo.get_expiring(within_days=3)
    ids = {s.id for s in expiring_list}

    assert exactly_now_sub.id not in ids, (
        "expires_at == now не должен попадать в окно 'скоро истекает' "
        "(условие expires_at > now строгое)."
    )
    assert just_after_now_sub.id in ids, (
        "expires_at на 1 микросекунду позже now должен попадать в окно."
    )


@pytest.mark.asyncio
async def test_get_expiring_boundary_exactly_at_window_edge_is_included(
    db_session: AsyncSession, monkeypatch
) -> None:
    """
    Правый край окна expires_at <= now + within_days должен включать
    подписку, истекающую РОВНО в этот момент (граница включительна),
    и исключать подписку на 1 микросекунду позже.
    """
    frozen_now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    _FrozenDatetime._frozen_now = frozen_now
    monkeypatch.setattr(subscriptions_module, "datetime", _FrozenDatetime)

    repo = SubscriptionRepo(db_session)
    user, server, tariff = await _make_base_entities(db_session, "win-hi")

    within_days = 3
    window_edge = frozen_now + timedelta(days=within_days)

    exactly_at_edge_sub = await _make_subscription(
        db_session, user, server, tariff, "exactly-at-edge", window_edge
    )
    just_past_edge_sub = await _make_subscription(
        db_session,
        user,
        server,
        tariff,
        "just-past-edge",
        window_edge + timedelta(microseconds=1),
    )
    await db_session.commit()

    expiring_list = await repo.get_expiring(within_days=within_days)
    ids = {s.id for s in expiring_list}

    assert exactly_at_edge_sub.id in ids, (
        "expires_at == now + within_days должен попадать в окно "
        "(правая граница включительна, expires_at <=)."
    )
    assert just_past_edge_sub.id not in ids, (
        "expires_at на 1 микросекунду позже правого края окна не "
        "должен попадать в выборку."
    )
