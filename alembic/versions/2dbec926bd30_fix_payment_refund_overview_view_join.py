"""fix payment refund overview view join

Revision ID: 2dbec926bd30
Revises: 3187f54b5a96
Create Date: 2026-09-06 03:48:06.438388

"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2dbec926bd30'
down_revision: Union[str, None] = '3187f54b5a96'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


BASE_DIR = Path(__file__).resolve().parents[2]
VIEWS_DIR = BASE_DIR / "database" / "sql" / "views"

_OLD_VIEW_SQL = """
CREATE OR REPLACE VIEW payment_refund_overview_view AS
SELECT
    p.id AS payment_id,
    p.status AS payment_status,
    p.amount,
    p.currency,
    p.paid_at,
    p.refundable,
    p.refunded_amount,
    u.id AS user_id,
    u.telegram_id,
    u.username,
    rr.id AS refund_request_id,
    rr.status AS refund_request_status,
    rr.reason AS refund_reason,
    r.id AS refund_id,
    r.status AS refund_status,
    r.amount AS refund_amount,
    r.completed_at AS refund_completed_at
FROM payments AS p
INNER JOIN users AS u ON p.user_id = u.id
LEFT JOIN refund_requests AS rr ON p.id = rr.payment_id
LEFT JOIN refunds AS r ON p.id = r.payment_id;
"""


def _read_sql(filename: str) -> str:
    return (VIEWS_DIR / filename).read_text(encoding="utf-8")


def upgrade() -> None:
    # Файл на диске уже содержит исправленный JOIN
    # (refunds -> refund_requests по refund_request_id, а не по payment_id),
    # CREATE OR REPLACE просто переопределяет view без DROP.
    op.execute(_read_sql("002_payment_refund_overview_view.up.sql"))


def downgrade() -> None:
    # Откат воспроизводит старую (ошибочную) версию явной строкой,
    # т.к. файл на диске к моменту отката уже будет содержать фикс.
    op.execute(_OLD_VIEW_SQL)
