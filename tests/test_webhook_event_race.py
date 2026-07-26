from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_test_engine
from database.enums import WebhookEventStatus
from database.repo.webhook_events import WebhookEventsRepo


@pytest_asyncio.fixture
async def concurrent_session_factory():
    engine = create_test_engine(pool_size=5)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _create_event(factory, provider: str, external_id: str):
    """
    WebhookEventsRepo.create_event идемпотентен по (provider,
    external_id): платёжный провайдер может продублировать вебхук
    (retry), а также два конкурентных воркера/запроса могут обрабатывать
    один и тот же входящий webhook параллельно. После фикса (SAVEPOINT +
    except IntegrityError) второй вызов должен получить уже созданную
    запись, а не создать дубликат и не упасть с необработанным
    исключением.
    """
    async with factory() as session:
        repo = WebhookEventsRepo(session)
        event = await repo.create_event(
            provider=provider,
            event_type="payment.succeeded",
            payload={"object": {"id": "yk-race-1"}},
            external_id=external_id,
            status=WebhookEventStatus.RECEIVED,
        )
        await session.commit()
        return event


@pytest.mark.asyncio
async def test_concurrent_webhook_same_external_id_creates_only_one_event(
    concurrent_session_factory,
):
    provider = "yookassa"
    shared_external_id = "yk-race-external-id-1"

    results = await asyncio.gather(
        _create_event(concurrent_session_factory, provider, shared_external_id),
        _create_event(concurrent_session_factory, provider, shared_external_id),
    )

    assert all(r is not None for r in results), (
        "WebhookEventsRepo.create_event должен вернуть WebhookEvent в "
        "обоих случаях, даже при гонке — исключение наружу не "
        "пробрасывается."
    )

    ids = {r.id for r in results}
    assert len(ids) == 1, (
        "Оба параллельных вызова с одинаковым (provider, external_id) "
        "должны вернуть один и тот же WebhookEvent.id — гонка не должна "
        "приводить к появлению двух разных записей и повторной "
        "обработке одного и того же события."
    )

    async with concurrent_session_factory() as check_session:
        pending = await WebhookEventsRepo(check_session).list_pending(
            provider=provider, limit=100
        )
        matching = [e for e in pending if e.external_id == shared_external_id]
        assert len(matching) == 1, (
            "В БД должна остаться ровно одна запись WebhookEvent с этим "
            "(provider, external_id) — гонка не должна приводить к "
            "дублированию."
        )
