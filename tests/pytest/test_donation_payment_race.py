from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_test_engine
from database.enums import PaymentProvider
from database.repo.payments import PaymentRepo
from database.repo.users import UserRepo
from domain.donation_metadata import build_donation_metadata
from services.payment import PaymentService


@pytest_asyncio.fixture
async def concurrent_session_factory():
    engine = create_test_engine(pool_size=5)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _create_donation_with_key(factory, user_id: int, idempotency_key: str):
    """
    PaymentService.create_payment сам по себе полностью идемпотентен:
    при гонке (IntegrityError на INSERT) он ловит её внутри и возвращает
    уже существующий Payment, а не пробрасывает исключение наружу.
    Поэтому здесь просто вызываем сервис — падать тут нечему.
    """
    async with factory() as session:
        service = PaymentService(session)
        metadata = build_donation_metadata(
            user=await UserRepo(session).get_by_id(user_id),
            amount=10000,
            currency="RUB",
        )
        payment = await service.create_payment(
            user_id=user_id,
            amount=10000,
            currency="RUB",
            provider=PaymentProvider.YOOKASSA,
            subscription_id=None,
            idempotency_key=idempotency_key,
            metadata_snapshot=metadata,
        )
        await session.commit()
        return payment


@pytest.mark.asyncio
async def test_concurrent_donation_same_idempotency_key_creates_only_one_payment(
    concurrent_session_factory,
):
    async with concurrent_session_factory() as setup_session:
        user = await UserRepo(setup_session).create(
            telegram_id=999_000_111,
            username="race_test_user",
        )
        await setup_session.commit()
        user_id = user.id

    shared_key = str(uuid.uuid4())

    results = await asyncio.gather(
        _create_donation_with_key(concurrent_session_factory, user_id, shared_key),
        _create_donation_with_key(concurrent_session_factory, user_id, shared_key),
    )

    assert all(r is not None for r in results), (
        "PaymentService.create_payment идемпотентен и должен вернуть Payment "
        "в обоих случаях, даже при гонке — исключение наружу не пробрасывается."
    )

    ids = {r.id for r in results}
    assert len(ids) == 1, (
        "Оба параллельных вызова с одинаковым idempotency_key должны "
        "вернуть один и тот же Payment.id — гонка не должна приводить "
        "к появлению двух разных записей."
    )

    async with concurrent_session_factory() as check_session:
        payments_in_db = await PaymentRepo(check_session).get_all_by_user(user_id)
        matching = [p for p in payments_in_db if p.idempotence_key == shared_key]
        assert len(matching) == 1, (
            "В БД должна остаться ровно одна запись Payment с этим "
            "idempotency_key — гонка не должна приводить к дублированию."
        )
