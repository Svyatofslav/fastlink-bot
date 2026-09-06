"""fix updated_at triggers: drop broken notifications_log trigger, add missing support_tickets trigger

Revision ID: 3187f54b5a96
Revises: 1adb3f0f1e8b
Create Date: 2026-09-05 21:42:00.752267

"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from alembic import op

BASE_DIR = Path(__file__).resolve().parents[2]
TRIGGERS_DIR = BASE_DIR / "database" / "sql" / "triggers"


def _read_sql(path: Path, filename: str) -> str:
    return (path / filename).read_text(encoding="utf-8")


# revision identifiers, used by Alembic.
revision: str = '3187f54b5a96'
down_revision: Union[str, None] = '1adb3f0f1e8b'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # notifications_log не имеет колонки updated_at — триггер был
    # ошибочно создан в 2b8081387338 и падал бы при первом UPDATE.
    # 001_updated_at_triggers.up.sql уже исправлен и больше его не
    # создаёт, но на уже применённых окружениях (прод) он физически
    # остался — удаляем явно.
    op.execute(
        "DROP TRIGGER IF EXISTS trg_notifications_log_set_updated_at "
        "ON notifications_log"
    )

    # support_tickets появилась позже 2b8081387338 в истории (8e9a1f1fa6c8),
    # поэтому не может быть частью 001-файла — добавляем отдельным файлом.
    op.execute(_read_sql(TRIGGERS_DIR, "003_support_tickets_updated_at_trigger.up.sql"))


def downgrade() -> None:
    op.execute(_read_sql(TRIGGERS_DIR, "003_support_tickets_updated_at_trigger.down.sql"))

    # trg_notifications_log_set_updated_at сознательно не восстанавливаем:
    # он был нерабочим (падал бы на первом же UPDATE), и его "откат"
    # не имеет смысла — по аналогии с downgrade() в 1adb3f0f1e8b.
