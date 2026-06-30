from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "dac2aeab7594"
down_revision: Union[str, None] = "522f84617ca9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("external_id", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_retry_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Уникальность внешнего события в рамках провайдера
    op.create_unique_constraint(
        "uq_webhook_events_provider_external_id",
        "webhook_events",
        ["provider", "external_id"],
    )

    # Индекс для выборки событий по статусу и провайдеру
    op.create_index(
        "ix_webhook_events_status_provider",
        "webhook_events",
        ["status", "provider"],
    )

    # Индекс по времени создания для чистки и отчётности
    op.create_index(
        "ix_webhook_events_created_at",
        "webhook_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_events_created_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_status_provider", table_name="webhook_events")
    op.drop_constraint(
        "uq_webhook_events_provider_external_id",
        "webhook_events",
        type_="unique",
    )
    op.drop_table("webhook_events")
