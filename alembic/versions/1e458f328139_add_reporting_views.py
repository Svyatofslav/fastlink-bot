"""add reporting views

Revision ID: 1e458f328139
Revises: 3818d475fc66
Create Date: 2026-07-03 21:24:36.431796

"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from alembic import op

BASE_DIR = Path(__file__).resolve().parents[2]
VIEWS_DIR = BASE_DIR / "database" / "sql" / "views"


# revision identifiers, used by Alembic.
revision: str = "1e458f328139"
down_revision: Union[str, None] = "3818d475fc66"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _read_sql(filename: str) -> str:
    return (VIEWS_DIR / filename).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_read_sql("001_active_subscriptions_view.up.sql"))
    op.execute(_read_sql("002_payment_refund_overview_view.up.sql"))


def downgrade() -> None:
    op.execute(_read_sql("002_payment_refund_overview_view.down.sql"))
    op.execute(_read_sql("001_active_subscriptions_view.down.sql"))
