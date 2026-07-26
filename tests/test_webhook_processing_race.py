from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from unittest.mock import AsyncMock, patch

from database.engine import create_test_engine
from database.enums import WebhookEventStatus
from database.repo.webhook_events import WebhookEventsRepo
from scheduler.jobs import process_webhook_events_with_session


@pytest_asyncio.fixture
async def concurrent_session_factory():
    engine = create_test_engine(pool_size=5)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_workers_process_same_event_only_once(
    concurrent_session_factory,
):
    """
    Если два воркера (например, старый и новый инстанс на деплое)
    одновременно вызовут process_webhook_events_with_session, они не
    должны оба обработать одно и то же RECEIVED-событие. list_pending
    использует FOR UPDATE SKIP LOCKED — второй воркер должен либо не
    получить это событие вообще (если первый уже его залочил), либо
    получить его только после того, как первый закоммитил построчно и
    статус перестал быть RECEIVED.
    """
    async with concurrent_session_factory() as setup_session:
        repo = WebhookEventsRepo(setup_session)
        event = await repo.create_event(
            provider="yookassa",
            event_type="payment.canceled",
            payload={"object": {"id": "yk-processing-race-1"}},
            external_id="yk-processing-race-external-1",
            status=WebhookEventStatus.RECEIVED,
        )
        await setup_session.commit()
        event_id = event.id

    call_count = 0
    call_lock = asyncio.Lock()

    async def _fake_handle_single_event(repo, ev, bot=None):
        nonlocal call_count
        async with call_lock:
            call_count += 1
        # Симулируем задержку обработки, чтобы увеличить окно гонки —
        # без искусственной задержки оба воркера могут завершиться
        # слишком быстро друг за другом и гонка не проявится стабильно.
        await asyncio.sleep(0.2)

    async def _run_worker():
        async with concurrent_session_factory() as session:
            with patch(
                "scheduler.jobs.handle_single_event",
                new=AsyncMock(side_effect=_fake_handle_single_event),
            ):
                await process_webhook_events_with_session(
                    session=session, provider="yookassa", limit=100
                )

    await asyncio.gather(_run_worker(), _run_worker())

    assert call_count == 1, (
        "Обработчик события должен быть вызван ровно один раз, "
        "несмотря на два параллельных воркера — FOR UPDATE SKIP LOCKED "
        "в list_pending должен гарантировать, что второй воркер не "
        "получит уже залоченное первым событие."
    )

    async with concurrent_session_factory() as check_session:
        repo = WebhookEventsRepo(check_session)
        pending = await repo.list_pending(provider="yookassa", limit=100)
        assert event_id not in [e.id for e in pending], (
            "После обработки событие не должно оставаться в статусе "
            "RECEIVED (list_pending его больше не возвращает)."
        )
