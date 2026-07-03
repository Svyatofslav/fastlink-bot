"""add webhook events audit trigger

Revision ID: 3818d475fc66
Revises: 2b8081387338
Create Date: 2026-07-03 20:45:38.725461

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
revision: str = "3818d475fc66"
down_revision: Union[str, None] = "2b8081387338"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(_read_sql(FUNCTIONS_DIR, "002_webhook_events_audit.up.sql"))
    op.execute(_read_sql(TRIGGERS_DIR, "002_webhook_events_audit_triggers.up.sql"))


def downgrade() -> None:
    op.execute(_read_sql(TRIGGERS_DIR, "002_webhook_events_audit_triggers.down.sql"))
    op.execute(_read_sql(FUNCTIONS_DIR, "002_webhook_events_audit.down.sql"))
