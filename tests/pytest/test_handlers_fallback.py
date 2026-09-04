from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from handlers.client.fallback import on_unrecognized_message
from tests.pytest.factories import make_user
from tests.pytest.helpers import make_message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_on_unrecognized_message_answers_and_shows_menu(
    db_session: AsyncSession,
) -> None:
    user = make_user()
    message = make_message("что это значит")

    with patch(
        "handlers.client.fallback.render_main_menu", new=AsyncMock()
    ) as render_menu_mock:
        await on_unrecognized_message(message, user, db_session)

    message.answer.assert_awaited_once()
    render_menu_mock.assert_awaited_once_with(message, user, db_session)
