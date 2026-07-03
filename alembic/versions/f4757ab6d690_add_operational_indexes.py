"""add operational indexes

Revision ID: f4757ab6d690
Revises: 34ece85a1048
Create Date: 2026-07-03 06:01:17.317070

"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from alembic import op

BASE_DIR = Path(__file__).resolve().parents[2]
SQL_DIR = BASE_DIR / "database" / "sql" / "indexes"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


# revision identifiers, used by Alembic.
revision: str = "f4757ab6d690"
down_revision: Union[str, None] = "34ece85a1048"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(_read_sql("001_add_operational_indexes.up.sql"))


def downgrade() -> None:
    op.execute(_read_sql("001_add_operational_indexes.down.sql"))
