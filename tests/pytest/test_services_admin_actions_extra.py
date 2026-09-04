from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from database.enums import AdminActionType, AdminEntityType
from services.admin_actions import AdminActionLogService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_log_login_calls_log_action_with_correct_type(
    db_session: AsyncSession,
) -> None:
    service = AdminActionLogService(db_session)
    service._repo.log = AsyncMock()

    await service.log_login(admin_id=42)

    service._repo.log.assert_awaited_once()
    call_kwargs = service._repo.log.await_args.kwargs
    assert call_kwargs["admin_id"] == 42
    assert call_kwargs["action"] == AdminActionType.LOGIN
    assert call_kwargs["entity_type"] == AdminEntityType.ADMIN.value
    assert call_kwargs["entity_id"] == 42


@pytest.mark.asyncio
async def test_log_logout_calls_log_action_with_correct_type(
    db_session: AsyncSession,
) -> None:
    service = AdminActionLogService(db_session)
    service._repo.log = AsyncMock()

    await service.log_logout(admin_id=42)

    service._repo.log.assert_awaited_once()
    call_kwargs = service._repo.log.await_args.kwargs
    assert call_kwargs["action"] == AdminActionType.LOGOUT
    assert call_kwargs["entity_type"] == AdminEntityType.ADMIN.value
