"""fix_donation_succeeded_enum_case

Revision ID: f798517c235b
Revises: f67b6c398276
Create Date: 2026-07-24 21:21:40.173254

"""

from __future__ import annotations

from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f798517c235b"
down_revision: Union[str, None] = "f67b6c398276"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'DONATION_SUCCEEDED'"
    )


def downgrade() -> None:
    pass
