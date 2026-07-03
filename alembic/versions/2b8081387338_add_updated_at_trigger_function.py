"""add updated_at trigger function

Revision ID: 2b8081387338
Revises: f4757ab6d690
Create Date: 2026-07-03 20:19:01.777503

"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from alembic import op

BASE_DIR = Path(__file__).resolve().parents[2]
FUNCTIONS_DIR = BASE_DIR / "database" / "sql" / "functions"
TRIGGERS_DIR = BASE_DIR / "database" / "sql" / "triggers"


def _read_sql(path: Path, filename: str) -> str:
    return (path / filename).read_text(encoding="utf-8")


# revision identifiers, used by Alembic.
revision: str = "2b8081387338"
down_revision: Union[str, None] = "f4757ab6d690"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(_read_sql(FUNCTIONS_DIR, "001_set_updated_at.up.sql"))
    op.execute(_read_sql(TRIGGERS_DIR, "001_updated_at_triggers.up.sql"))


def downgrade() -> None:
    op.execute(_read_sql(TRIGGERS_DIR, "001_updated_at_triggers.down.sql"))
    op.execute(_read_sql(FUNCTIONS_DIR, "001_set_updated_at.down.sql"))
