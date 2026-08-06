from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_test_engine
from database.repo.users import UserRepo


@pytest_asyncio.fixture
async def concurrent_session_factory():
    engine = create_test_engine(pool_size=5)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


class _FakeTelegramUser:
    """
    Минимальная заглушка aiogram.types.User — get_or_create обращается
    только к этим полям.
    """

    def __init__(self, telegram_id: int) -> None:
        self.id = telegram_id
        self.username = "race_user"
        self.first_name = "Race"
        self.last_name = "Condition"
        self.language_code = "ru"


async def _get_or_create(factory, telegram_id: int):
    """
    UserRepo.get_or_create идемпотентен по telegram_id: при гонке двух
    одновременных /start от одного и того же пользователя второй вызов
    должен получить уже созданного User, а не упасть или создать дубликат.
    """
    async with factory() as session:
        repo = UserRepo(session)
        user, created = await repo.get_or_create(_FakeTelegramUser(telegram_id))
        await session.commit()
        return user, created


@pytest.mark.asyncio
async def test_concurrent_start_same_telegram_id_creates_only_one_user(
    concurrent_session_factory,
):
    shared_telegram_id = 999_000_333

    results = await asyncio.gather(
        _get_or_create(concurrent_session_factory, shared_telegram_id),
        _get_or_create(concurrent_session_factory, shared_telegram_id),
    )

    users = [r[0] for r in results]
    created_flags = [r[1] for r in results]

    assert all(u is not None for u in users), (
        "UserRepo.get_or_create должен вернуть User в обоих случаях, "
        "даже при гонке — исключение наружу не пробрасывается."
    )

    ids = {u.id for u in users}
    assert len(ids) == 1, (
        "Оба параллельных вызова /start с одинаковым telegram_id должны "
        "вернуть один и тот же User.id — гонка не должна приводить "
        "к появлению двух разных записей."
    )

    assert sum(created_flags) == 1, (
        "Ровно один из двух параллельных вызовов должен реально создать "
        "нового пользователя (created=True); второй должен получить "
        "уже существующего (created=False) через fallback после "
        "IntegrityError."
    )

    async with concurrent_session_factory() as check_session:
        matching = [
            u
            for u in await UserRepo(check_session).get_all_active()
            if u.telegram_id == shared_telegram_id
        ]
        assert len(matching) == 1, (
            "В БД должна остаться ровно одна запись User с этим "
            "telegram_id — гонка не должна приводить к дублированию."
        )
