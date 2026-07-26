from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import NotificationType


@pytest.mark.asyncio
async def test_all_notification_type_members_exist_in_pg_enum(
    db_session: AsyncSession,
) -> None:
    """
    Защита от расхождения между Python NotificationType(StrEnum) и реальными
    значениями PostgreSQL enum notification_type (SQLAlchemy Enum по умолчанию
    пишет .name члена, а не .value — легко перепутать в миграции).
    """
    result = await db_session.execute(
        text(
            "SELECT enumlabel FROM pg_enum "
            "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
            "WHERE pg_type.typname = 'notification_type'"
        )
    )
    pg_values = {row[0] for row in result.fetchall()}
    python_names = {member.name for member in NotificationType}

    missing_in_pg = python_names - pg_values
    assert not missing_in_pg, f"Отсутствуют в PG enum: {missing_in_pg}"
