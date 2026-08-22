from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from database.enums import (
    AdminActionType,
    DisabledReason,
    NotificationDeliveryStatus,
    NotificationType,
    PaymentProvider,
    PaymentStatus,
    RefundRequestStatus,
    RefundStatus,
    SubscriptionStatus,
    SupportSenderType,
    SupportTicketCategory,
    SupportTicketStatus,
    WebhookEventStatus,
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="ru"
    )
    is_banned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_active_message_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    secretword_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admins.id", ondelete="SET NULL"),
        nullable=True,
    )


class Server(TimestampMixin, Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emoji: Mapped[str | None] = mapped_column(String(8), nullable=True)
    marzban_node_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metrics_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    inbound_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="100"
    )

    __table_args__ = (
        Index("ix_servers_is_active", "is_active"),
        Index("ix_servers_sort_order", "sort_order"),
    )


class Tariff(TimestampMixin, Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    server_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("servers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    data_limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="RUB"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="100"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_tariffs_is_active", "is_active"),
        Index("ix_tariffs_sort_order", "sort_order"),
    )


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    server_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("servers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tariff_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tariffs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    marzban_username: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SqlEnum(SubscriptionStatus, name="subscription_status"),
        nullable=False,
        default=SubscriptionStatus.PENDING,
    )
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    data_limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data_used_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    auto_renew: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    subscription_url: Mapped[str] = mapped_column(Text, nullable=False)
    disabled_reason: Mapped[DisabledReason | None] = mapped_column(
        SqlEnum(DisabledReason, name="disabled_reason"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "server_id", "marzban_username", name="uq_subscriptions_server_username"
        ),
        Index("ix_subscriptions_status", "status"),
        Index("ix_subscriptions_user_status", "user_id", "status"),
        Index("ix_subscriptions_marzban_username", "marzban_username"),
        Index("ix_subscriptions_status_expires_at", "status", "expires_at"),
    )


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        SqlEnum(PaymentProvider, name="payment_provider"),
        nullable=False,
        default=PaymentProvider.YOOKASSA,
    )
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    confirmation_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="RUB"
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SqlEnum(PaymentStatus, name="payment_status"),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    idempotence_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    metadata_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    refundable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    refunded_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )

    __table_args__ = (
        Index("ix_payments_status", "status"),
        Index("ix_payments_user_created_at_desc", "user_id", desc("created_at")),
        Index(
            "ix_payments_subscription_created_at_desc",
            "subscription_id",
            desc("created_at"),
        ),
    )


class RefundRequest(TimestampMixin, Base):
    __tablename__ = "refund_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RefundRequestStatus] = mapped_column(
        SqlEnum(RefundRequestStatus, name="refund_request_status"),
        nullable=False,
        default=RefundRequestStatus.NEW,
    )
    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admins.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_refund_requests_status", "status"),
        Index(
            "ix_refund_requests_status_created_at_desc",
            "status",
            desc("created_at"),
        ),
    )


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refund_request_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("refund_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        SqlEnum(PaymentProvider, name="payment_provider", create_type=False),
        nullable=False,
        default=PaymentProvider.YOOKASSA,
    )
    provider_refund_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="RUB"
    )
    status: Mapped[RefundStatus] = mapped_column(
        SqlEnum(RefundStatus, name="refund_status"),
        nullable=False,
        default=RefundStatus.PENDING,
    )
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_refunds_status", "status"),
        Index(
            "uq_refunds_active_per_request",
            "refund_request_id",
            unique=True,
            postgresql_where=text(
                "status <> 'CANCELED' AND refund_request_id IS NOT NULL"
            ),
        ),
    )


class SupportTicket(TimestampMixin, Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[SupportTicketCategory] = mapped_column(
        SqlEnum(SupportTicketCategory, name="support_ticket_category"),
        nullable=False,
        default=SupportTicketCategory.GENERAL,
    )
    status: Mapped[SupportTicketStatus] = mapped_column(
        SqlEnum(SupportTicketStatus, name="support_ticket_status"),
        nullable=False,
        default=SupportTicketStatus.NEW,
    )
    assigned_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admins.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_support_tickets_status", "status"),
        Index("ix_support_tickets_user_status", "user_id", "status"),
        Index("ix_support_tickets_assigned_admin_id", "assigned_admin_id"),
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type: Mapped[SupportSenderType] = mapped_column(
        SqlEnum(SupportSenderType, name="support_sender_type"),
        nullable=False,
    )
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_support_messages_ticket_id", "ticket_id"),
        Index("ix_support_messages_created_at", "created_at"),
    )


class NotificationLog(Base):
    __tablename__ = "notifications_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        SqlEnum(NotificationType, name="notification_type"),
        nullable=False,
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    delivery_status: Mapped[NotificationDeliveryStatus] = mapped_column(
        SqlEnum(NotificationDeliveryStatus, name="notification_delivery_status"),
        nullable=False,
        default=NotificationDeliveryStatus.SENT,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "subscription_id", "type", name="uq_notifications_dedup"
        ),
        Index("ix_notifications_log_type", "type"),
    )


class AdminActionLog(TimestampMixin, Base):
    __tablename__ = "admin_actions_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("admins.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[AdminActionType] = mapped_column(
        SqlEnum(AdminActionType, name="admin_action_type"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    payload_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_admin_actions_log_action", "action"),
        Index("ix_admin_actions_log_entity_type", "entity_type"),
        Index("ix_admin_actions_log_entity_id", "entity_id"),
    )


class WebhookEvent(TimestampMixin, Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[WebhookEventStatus] = mapped_column(
        SqlEnum(WebhookEventStatus, name="webhook_event_status"),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    last_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_id",
            name="uq_webhook_events_provider_external_id",
        ),
        Index("ix_webhook_events_status_provider", "status", "provider"),
        Index("ix_webhook_events_created_at", "created_at"),
    )


class WebhookEventAudit(Base):
    __tablename__ = "webhook_events_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("webhook_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    old_row: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_row: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_webhook_events_audit_event_id", "event_id"),
        Index("ix_webhook_events_audit_changed_at", "changed_at"),
    )
