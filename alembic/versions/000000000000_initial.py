"""initial

Revision ID: 000000000000
Revises:
Create Date: 2026-06-30 08:12:00

"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "000000000000"
down_revision: Union[str, None] = None
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Enum types: create once
    for name, values in [
        ("subscription_status", ["PENDING", "ACTIVE", "DISABLED", "EXPIRED"]),
        (
            "disabled_reason",
            [
                "EXPIRED",
                "REFUNDED",
                "ADMIN_DISABLED",
                "FRAUD_SUSPECTED",
                "PAYMENT_CANCELED",
                "SYSTEM_ERROR",
            ],
        ),
        ("payment_provider", ["YOOKASSA"]),
        (
            "payment_status",
            [
                "PENDING",
                "WAITING_FOR_CAPTURE",
                "SUCCEEDED",
                "CANCELED",
                "REFUNDED_PARTIALLY",
                "REFUNDED_FULLY",
            ],
        ),
        (
            "refund_request_status",
            ["NEW", "IN_REVIEW", "APPROVED", "REJECTED", "PROCESSED", "FAILED"],
        ),
        ("refund_status", ["PENDING", "SUCCEEDED", "FAILED", "CANCELED"]),
        (
            "notification_type",
            [
                "SUB_EXPIRES_3D",
                "SUB_EXPIRES_1D",
                "TRAFFIC_80",
                "TRAFFIC_95",
                "TRAFFIC_100",
                "REFUND_PROCESSED",
                "PAYMENT_SUCCEEDED",
            ],
        ),
        ("notification_delivery_status", ["SENT", "FAILED"]),
        (
            "admin_action_type",
            [
                "LOGIN",
                "LOGOUT",
                "CREATE_ADMIN",
                "UPDATE_ADMIN",
                "DISABLE_ADMIN",
                "ENABLE_ADMIN",
                "CREATE_SERVER",
                "UPDATE_SERVER",
                "DELETE_SERVER",
                "CREATE_TARIFF",
                "UPDATE_TARIFF",
                "DELETE_TARIFF",
                "BAN_USER",
                "UNBAN_USER",
                "DISABLE_SUBSCRIPTION",
                "ENABLE_SUBSCRIPTION",
                "APPROVE_REFUND",
                "REJECT_REFUND",
                "PROCESS_REFUND",
            ],
        ),
        ("webhook_event_status", ["RECEIVED", "PROCESSING", "DONE", "FAILED"]),
    ]:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # Enum instances (no CREATE TYPE)
    subscription_status_enum = postgresql.ENUM(
        "PENDING",
        "ACTIVE",
        "DISABLED",
        "EXPIRED",
        name="subscription_status",
        create_type=False,
    )
    disabled_reason_enum = postgresql.ENUM(
        "EXPIRED",
        "REFUNDED",
        "ADMIN_DISABLED",
        "FRAUD_SUSPECTED",
        "PAYMENT_CANCELED",
        "SYSTEM_ERROR",
        name="disabled_reason",
        create_type=False,
    )
    payment_provider_enum = postgresql.ENUM(
        "YOOKASSA",
        name="payment_provider",
        create_type=False,
    )
    payment_status_enum = postgresql.ENUM(
        "PENDING",
        "WAITING_FOR_CAPTURE",
        "SUCCEEDED",
        "CANCELED",
        "REFUNDED_PARTIALLY",
        "REFUNDED_FULLY",
        name="payment_status",
        create_type=False,
    )
    refund_request_status_enum = postgresql.ENUM(
        "NEW",
        "IN_REVIEW",
        "APPROVED",
        "REJECTED",
        "PROCESSED",
        "FAILED",
        name="refund_request_status",
        create_type=False,
    )
    refund_status_enum = postgresql.ENUM(
        "PENDING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
        name="refund_status",
        create_type=False,
    )
    notification_type_enum = postgresql.ENUM(
        "SUB_EXPIRES_3D",
        "SUB_EXPIRES_1D",
        "TRAFFIC_80",
        "TRAFFIC_95",
        "TRAFFIC_100",
        "REFUND_PROCESSED",
        "PAYMENT_SUCCEEDED",
        name="notification_type",
        create_type=False,
    )
    notification_delivery_status_enum = postgresql.ENUM(
        "SENT",
        "FAILED",
        name="notification_delivery_status",
        create_type=False,
    )
    admin_action_type_enum = postgresql.ENUM(
        "LOGIN",
        "LOGOUT",
        "CREATE_ADMIN",
        "UPDATE_ADMIN",
        "DISABLE_ADMIN",
        "ENABLE_ADMIN",
        "CREATE_SERVER",
        "UPDATE_SERVER",
        "DELETE_SERVER",
        "CREATE_TARIFF",
        "UPDATE_TARIFF",
        "DELETE_TARIFF",
        "BAN_USER",
        "UNBAN_USER",
        "DISABLE_SUBSCRIPTION",
        "ENABLE_SUBSCRIPTION",
        "APPROVE_REFUND",
        "REJECT_REFUND",
        "PROCESS_REFUND",
        name="admin_action_type",
        create_type=False,
    )
    webhook_event_status_enum = postgresql.ENUM(
        "RECEIVED",
        "PROCESSING",
        "DONE",
        "FAILED",
        name="webhook_event_status",
        create_type=False,
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("language_code", sa.String(8), nullable=False, server_default="ru"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # убираем отдельный UniqueConstraint, как это делает schema_check
        # sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # admins
    op.create_table(
        "admins",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("login", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("secretword_hash", sa.Text(), nullable=False),
        sa.Column(
            "is_superadmin", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_by_admin_id",
            sa.BigInteger(),
            sa.ForeignKey("admins.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # убираем UniqueConstraint по telegram_id, оставляем только по login
        # sa.UniqueConstraint("telegram_id", name="uq_admins_telegram_id"),
        sa.UniqueConstraint("login", name="uq_admins_login"),
    )
    op.create_index("ix_admins_telegram_id", "admins", ["telegram_id"], unique=True)

    # servers
    op.create_table(
        "servers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country_code", sa.String(8), nullable=True),
        sa.Column("country_name", sa.String(64), nullable=True),
        sa.Column("emoji", sa.String(8), nullable=True),
        sa.Column("api_url", sa.Text(), nullable=False),
        sa.Column("api_token", sa.Text(), nullable=False),
        sa.Column("metrics_url", sa.Text(), nullable=True),
        sa.Column("metrics_token", sa.Text(), nullable=True),
        sa.Column("inbound_tag", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_servers_is_active", "servers", ["is_active"])
    op.create_index("ix_servers_sort_order", "servers", ["sort_order"])

    # tariffs
    op.create_table(
        "tariffs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "server_id",
            sa.BigInteger(),
            sa.ForeignKey("servers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("data_limit_bytes", sa.BigInteger(), nullable=False),
        sa.Column("price_amount", sa.BigInteger(), nullable=False),
        sa.Column("price_currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_tariffs_server_id", "tariffs", ["server_id"])
    op.create_index("ix_tariffs_is_active", "tariffs", ["is_active"])
    op.create_index("ix_tariffs_sort_order", "tariffs", ["sort_order"])

    # subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_id",
            sa.BigInteger(),
            sa.ForeignKey("servers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "tariff_id",
            sa.BigInteger(),
            sa.ForeignKey("tariffs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("marzban_username", sa.String(128), nullable=False),
        sa.Column(
            "status",
            subscription_status_enum,
            nullable=False,
            # убираем server_default, автоген это предлагает
            # server_default="PENDING",
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_limit_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "data_used_bytes", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("subscription_url", sa.Text(), nullable=False),
        sa.Column("disabled_reason", disabled_reason_enum, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "server_id", "marzban_username", name="uq_subscriptions_server_username"
        ),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_server_id", "subscriptions", ["server_id"])
    op.create_index("ix_subscriptions_tariff_id", "subscriptions", ["tariff_id"])
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["expires_at"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index(
        "ix_subscriptions_user_status", "subscriptions", ["user_id", "status"]
    )
    op.create_index(
        "ix_subscriptions_marzban_username", "subscriptions", ["marzban_username"]
    )

    # payments
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.BigInteger(),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "provider",
            payment_provider_enum,
            nullable=False,
            # server_default="YOOKASSA",
        ),
        sa.Column("provider_payment_id", sa.String(128), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column(
            "status",
            payment_status_enum,
            nullable=False,
            # server_default="PENDING",
        ),
        sa.Column("idempotence_key", sa.String(128), nullable=False),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refundable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "refunded_amount", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "provider_payment_id", name="uq_payments_provider_payment_id"
        ),
        sa.UniqueConstraint("idempotence_key", name="uq_payments_idempotence_key"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_subscription_id", "payments", ["subscription_id"])
    op.create_index("ix_payments_paid_at", "payments", ["paid_at"])
    op.create_index("ix_payments_status", "payments", ["status"])

    # refund_requests
    op.create_table(
        "refund_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_id",
            sa.BigInteger(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.BigInteger(),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            refund_request_status_enum,
            nullable=False,
            # server_default="NEW",
        ),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_by_admin_id",
            sa.BigInteger(),
            sa.ForeignKey("admins.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_refund_requests_user_id", "refund_requests", ["user_id"])
    op.create_index("ix_refund_requests_payment_id", "refund_requests", ["payment_id"])
    op.create_index(
        "ix_refund_requests_subscription_id", "refund_requests", ["subscription_id"]
    )
    op.create_index(
        "ix_refund_requests_reviewed_by_admin_id",
        "refund_requests",
        ["reviewed_by_admin_id"],
    )
    op.create_index("ix_refund_requests_status", "refund_requests", ["status"])
    # Условный уникальный индекс не создаём, как предлагает schema_check
    # op.execute(
    #     """
    #     CREATE UNIQUE INDEX uix_refund_requests_one_pending
    #     ON refund_requests (subscription_id)
    #     WHERE status = 'NEW'
    #     """
    # )

    # refunds
    op.create_table(
        "refunds",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "payment_id",
            sa.BigInteger(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "refund_request_id",
            sa.BigInteger(),
            sa.ForeignKey("refund_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "provider",
            payment_provider_enum,
            nullable=False,
            # server_default="YOOKASSA",
        ),
        sa.Column("provider_refund_id", sa.String(128), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column(
            "status",
            refund_status_enum,
            nullable=False,
            # server_default="PENDING",
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("provider_refund_id", name="uq_refunds_provider_refund_id"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])
    op.create_index("ix_refunds_refund_request_id", "refunds", ["refund_request_id"])
    op.create_index("ix_refunds_status", "refunds", ["status"])

    # notifications_log
    op.create_table(
        "notifications_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.BigInteger(),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", notification_type_enum, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "delivery_status",
            notification_delivery_status_enum,
            nullable=False,
            # server_default="SENT",
        ),
        sa.UniqueConstraint(
            "user_id", "subscription_id", "type", name="uq_notifications_dedup"
        ),
    )
    op.create_index("ix_notifications_log_user_id", "notifications_log", ["user_id"])
    op.create_index(
        "ix_notifications_log_subscription_id", "notifications_log", ["subscription_id"]
    )
    op.create_index("ix_notifications_log_type", "notifications_log", ["type"])

    # admin_actions_log
    op.create_table(
        "admin_actions_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "admin_id",
            sa.BigInteger(),
            sa.ForeignKey("admins.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", admin_action_type_enum, nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("payload_before", sa.JSON(), nullable=True),
        sa.Column("payload_after", sa.JSON(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_admin_actions_log_admin_id", "admin_actions_log", ["admin_id"])
    op.create_index("ix_admin_actions_log_action", "admin_actions_log", ["action"])
    op.create_index(
        "ix_admin_actions_log_entity_type", "admin_actions_log", ["entity_type"]
    )
    op.create_index(
        "ix_admin_actions_log_entity_id", "admin_actions_log", ["entity_id"]
    )

    # webhook_events
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("status", webhook_event_status_enum, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "provider",
            "external_id",
            name="uq_webhook_events_provider_external_id",
        ),
    )
    op.create_index(
        "ix_webhook_events_status_provider",
        "webhook_events",
        ["status", "provider"],
    )
    op.create_index("ix_webhook_events_created_at", "webhook_events", ["created_at"])


def downgrade() -> None:
    # Drop tables in dependency-safe order
    op.drop_index("ix_webhook_events_created_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_status_provider", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_table("admin_actions_log")
    op.drop_table("notifications_log")
    op.drop_table("refunds")
    op.drop_table("refund_requests")
    op.drop_table("payments")
    op.drop_table("subscriptions")
    op.drop_table("tariffs")
    op.drop_table("servers")
    op.drop_table("admins")
    op.drop_table("users")

    # Drop enum types
    for type_name in [
        "admin_action_type",
        "notification_delivery_status",
        "notification_type",
        "refund_status",
        "refund_request_status",
        "payment_status",
        "payment_provider",
        "disabled_reason",
        "subscription_status",
        "webhook_event_status",
    ]:
        op.execute(f'DROP TYPE IF EXISTS "{type_name}" CASCADE')
