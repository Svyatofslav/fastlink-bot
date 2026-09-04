from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from database.enums import RefundRequestStatus
from database.repo.refund_requests import RefundRequestRepo
from tests.pytest.factories import (
    make_payment,
    make_server,
    make_subscription,
    make_tariff,
    make_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_refund_request(
    db_session: AsyncSession,
    *,
    user_id: int,
    payment_id: int,
    subscription_id: int | None = None,
    status: RefundRequestStatus = RefundRequestStatus.NEW,
):
    repo = RefundRequestRepo(db_session)
    return await repo.create(
        user_id=user_id,
        payment_id=payment_id,
        subscription_id=subscription_id,
        reason="test reason",
        status=status,
        admin_comment=None,
        reviewed_by_admin_id=None,
        reviewed_at=None,
    )


@pytest.mark.asyncio
async def test_get_by_subscription_returns_matching_ordered(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    server = make_server()
    db_session.add_all([user, server])
    await db_session.flush()
    tariff = make_tariff(server_id=server.id)
    db_session.add(tariff)
    await db_session.flush()

    sub_a = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    sub_b = make_subscription(user_id=user.id, server_id=server.id, tariff_id=tariff.id)
    db_session.add_all([sub_a, sub_b])
    await db_session.flush()

    payment1 = make_payment(user_id=user.id)
    payment2 = make_payment(user_id=user.id)
    db_session.add_all([payment1, payment2])
    await db_session.flush()

    rr1 = await _make_refund_request(
        db_session, user_id=user.id, payment_id=payment1.id, subscription_id=sub_a.id
    )
    rr2 = await _make_refund_request(
        db_session, user_id=user.id, payment_id=payment2.id, subscription_id=sub_a.id
    )
    other = await _make_refund_request(
        db_session, user_id=user.id, payment_id=payment1.id, subscription_id=sub_b.id
    )
    await db_session.commit()

    repo = RefundRequestRepo(db_session)
    result = await repo.get_by_subscription(sub_a.id)
    ids = {r.id for r in result}

    assert rr1.id in ids
    assert rr2.id in ids
    assert other.id not in ids


@pytest.mark.asyncio
async def test_get_by_user_returns_only_that_users_requests(
    db_session: AsyncSession,
) -> None:
    user1 = make_user()
    user2 = make_user()
    db_session.add_all([user1, user2])
    await db_session.flush()
    payment1 = make_payment(user_id=user1.id)
    payment2 = make_payment(user_id=user2.id)
    db_session.add_all([payment1, payment2])
    await db_session.flush()

    rr1 = await _make_refund_request(
        db_session, user_id=user1.id, payment_id=payment1.id
    )
    rr2 = await _make_refund_request(
        db_session, user_id=user2.id, payment_id=payment2.id
    )
    await db_session.commit()

    repo = RefundRequestRepo(db_session)
    result = await repo.get_by_user(user1.id)
    ids = {r.id for r in result}

    assert rr1.id in ids
    assert rr2.id not in ids


@pytest.mark.asyncio
async def test_get_pending_returns_only_new_status(db_session: AsyncSession) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()
    payment1 = make_payment(user_id=user.id)
    payment2 = make_payment(user_id=user.id)
    db_session.add_all([payment1, payment2])
    await db_session.flush()

    new_request = await _make_refund_request(
        db_session,
        user_id=user.id,
        payment_id=payment1.id,
        status=RefundRequestStatus.NEW,
    )
    approved_request = await _make_refund_request(
        db_session,
        user_id=user.id,
        payment_id=payment2.id,
        status=RefundRequestStatus.APPROVED,
    )
    await db_session.commit()

    repo = RefundRequestRepo(db_session)
    result = await repo.get_pending()
    ids = {r.id for r in result}

    assert new_request.id in ids
    assert approved_request.id not in ids


@pytest.mark.asyncio
async def test_set_status_updates_status_and_extra_fields(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    db_session.add(user)
    await db_session.flush()
    payment = make_payment(user_id=user.id)
    db_session.add(payment)
    await db_session.flush()

    refund_request = await _make_refund_request(
        db_session, user_id=user.id, payment_id=payment.id
    )
    await db_session.commit()

    repo = RefundRequestRepo(db_session)
    updated = await repo.set_status(
        refund_request,
        RefundRequestStatus.APPROVED,
        admin_comment="looks good",
    )

    assert updated.status == RefundRequestStatus.APPROVED
    assert updated.admin_comment == "looks good"
