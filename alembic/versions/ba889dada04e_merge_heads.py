"""merge heads

Revision ID: ba889dada04e
Revises: 20240629_mark_servers_tokens_encrypted, dac2aeab7594
Create Date: 2026-06-30 05:24:14.986701

"""

from __future__ import annotations

from typing import Union


# revision identifiers, used by Alembic.
revision: str = "ba889dada04e"
down_revision: Union[str, None] = (
    "20240629_mark_servers_tokens_encrypted",
    "dac2aeab7594",
)
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
