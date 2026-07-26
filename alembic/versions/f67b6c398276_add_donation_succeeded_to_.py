"""add donation_succeeded to notificationtype enum

Revision ID: f67b6c398276
Revises: 8e9a1f1fa6c8
Create Date: 2026-07-24 01:53:15.898462

"""

from __future__ import annotations

from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f67b6c398276"
down_revision: Union[str, None] = "8e9a1f1fa6c8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'donation_succeeded'"
    )


def downgrade() -> None:
    pass
