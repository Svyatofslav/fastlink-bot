"""change json fields to jsonb

Revision ID: 34ece85a1048
Revises: bb96a18f9f36
Create Date: 2026-07-03 05:13:17.415363

"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "34ece85a1048"
down_revision: Union[str, None] = "bb96a18f9f36"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.alter_column(
        "admin_actions_log",
        "payload_before",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="payload_before::jsonb",
    )
    op.alter_column(
        "admin_actions_log",
        "payload_after",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="payload_after::jsonb",
    )
    op.alter_column(
        "notifications_log",
        "payload",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="payload::jsonb",
    )
    op.alter_column(
        "payments",
        "metadata_snapshot",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="metadata_snapshot::jsonb",
    )
    op.alter_column(
        "refunds",
        "raw_payload",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="raw_payload::jsonb",
    )
    op.alter_column(
        "webhook_events",
        "payload",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        postgresql_using="payload::jsonb",
    )
    op.alter_column(
        "webhook_events_audit",
        "old_row",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="old_row::jsonb",
    )
    op.alter_column(
        "webhook_events_audit",
        "new_row",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="new_row::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "webhook_events_audit",
        "new_row",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="new_row::json",
    )
    op.alter_column(
        "webhook_events_audit",
        "old_row",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="old_row::json",
    )
    op.alter_column(
        "webhook_events",
        "payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=False,
        postgresql_using="payload::json",
    )
    op.alter_column(
        "refunds",
        "raw_payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="raw_payload::json",
    )
    op.alter_column(
        "payments",
        "metadata_snapshot",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="metadata_snapshot::json",
    )
    op.alter_column(
        "notifications_log",
        "payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="payload::json",
    )
    op.alter_column(
        "admin_actions_log",
        "payload_after",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="payload_after::json",
    )
    op.alter_column(
        "admin_actions_log",
        "payload_before",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="payload_before::json",
    )
