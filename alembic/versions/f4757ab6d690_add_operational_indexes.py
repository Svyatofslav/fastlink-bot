"""add operational indexes

Revision ID: f4757ab6d690
Revises: 34ece85a1048
Create Date: 2026-07-03 06:01:17.317070

"""

from __future__ import annotations

from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f4757ab6d690"
down_revision: Union[str, None] = "34ece85a1048"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_status_expires_at "
        "ON subscriptions (status, expires_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_payments_user_created_at_desc "
        "ON payments (user_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_payments_subscription_created_at_desc "
        "ON payments (subscription_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_refund_requests_status_created_at_desc "
        "ON refund_requests (status, created_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_refund_requests_status_created_at_desc;")
    op.execute("DROP INDEX IF EXISTS ix_payments_subscription_created_at_desc;")
    op.execute("DROP INDEX IF EXISTS ix_payments_user_created_at_desc;")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_status_expires_at;")
