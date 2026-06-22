"""initial

Revision ID: 522f84617ca9
Revises:
Create Date: 2026-06-22 17:33:35.678032

"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '522f84617ca9'
down_revision: Union[str, None] = None
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:

    op.create_table(
        'users',
        sa.Column('id',           sa.BigInteger(), primary_key=True),
        sa.Column('telegram_id',  sa.BigInteger(), nullable=False),
        sa.Column('username',     sa.String(64),   nullable=True),
        sa.Column('first_name',   sa.String(128),  nullable=True),
        sa.Column('last_name',    sa.String(128),  nullable=True),
        sa.Column('language_code',sa.String(8),    nullable=False, server_default='ru'),
        sa.Column('is_banned',    sa.Boolean(),    nullable=False, server_default='false'),
        sa.Column('is_active',    sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('telegram_id', name='uq_users_telegram_id'),
    )
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'])

    op.create_table(
        'admins',
        sa.Column('id',                  sa.BigInteger(), primary_key=True),
        sa.Column('telegram_id',         sa.BigInteger(), nullable=False),
        sa.Column('username',            sa.String(64),  nullable=True),
        sa.Column('login',               sa.String(64),  nullable=False),
        sa.Column('password_hash',       sa.Text(),      nullable=False),
        sa.Column('secret_word_hash',    sa.Text(),      nullable=False),
        sa.Column('is_superadmin',       sa.Boolean(),   nullable=False, server_default='false'),
        sa.Column('is_active',           sa.Boolean(),   nullable=False, server_default='true'),
        sa.Column('created_by_admin_id', sa.BigInteger(),
                  sa.ForeignKey('admins.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at',  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('telegram_id', name='uq_admins_telegram_id'),
        sa.UniqueConstraint('login',       name='uq_admins_login'),
    )
    op.create_index('ix_admins_telegram_id', 'admins', ['telegram_id'])

    op.create_table(
        'servers',
        sa.Column('id',           sa.BigInteger(), primary_key=True),
        sa.Column('name',         sa.String(128),  nullable=False),
        sa.Column('country_code', sa.String(8),    nullable=True),
        sa.Column('country_name', sa.String(64),   nullable=True),
        sa.Column('emoji',        sa.String(8),    nullable=True),
        sa.Column('api_url',      sa.Text(),       nullable=False),
        sa.Column('api_token',    sa.Text(),       nullable=False),
        sa.Column('metrics_url',  sa.Text(),       nullable=True),
        sa.Column('metrics_token',sa.Text(),       nullable=True),
        sa.Column('inbound_tag',  sa.String(128),  nullable=False),
        sa.Column('is_active',    sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('sort_order',   sa.Integer(),    nullable=False, server_default='100'),
        sa.Column('created_at',   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_servers_is_active',  'servers', ['is_active'])
    op.create_index('ix_servers_sort_order', 'servers', ['sort_order'])

    op.create_table(
        'tariffs',
        sa.Column('id',              sa.BigInteger(), primary_key=True),
        sa.Column('server_id',       sa.BigInteger(),
                  sa.ForeignKey('servers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name',            sa.String(128), nullable=False),
        sa.Column('duration_days',   sa.Integer(),   nullable=False),
        sa.Column('data_limit_bytes',sa.BigInteger(),nullable=False),
        sa.Column('price_amount',    sa.BigInteger(),nullable=False),
        sa.Column('price_currency',  sa.String(3),   nullable=False, server_default='RUB'),
        sa.Column('is_active',       sa.Boolean(),   nullable=False, server_default='true'),
        sa.Column('sort_order',      sa.Integer(),   nullable=False, server_default='100'),
        sa.Column('description',     sa.Text(),      nullable=True),
        sa.Column('created_at',      sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',      sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_tariffs_server_id',  'tariffs', ['server_id'])
    op.create_index('ix_tariffs_is_active',  'tariffs', ['is_active'])
    op.create_index('ix_tariffs_sort_order', 'tariffs', ['sort_order'])

    op.create_table(
        'subscriptions',
        sa.Column('id',               sa.BigInteger(), primary_key=True),
        sa.Column('user_id',          sa.BigInteger(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('server_id',        sa.BigInteger(),
                  sa.ForeignKey('servers.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('tariff_id',        sa.BigInteger(),
                  sa.ForeignKey('tariffs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('marzban_username', sa.String(128), nullable=False),
        sa.Column('status',           sa.Enum('pending','active','disabled','expired',
                                              name='subscriptionstatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('starts_at',        sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at',       sa.DateTime(timezone=True), nullable=True),
        sa.Column('data_limit_bytes', sa.BigInteger(), nullable=False),
        sa.Column('data_used_bytes',  sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('auto_renew',       sa.Boolean(),    nullable=False, server_default='false'),
        sa.Column('subscription_url', sa.Text(),       nullable=False),
        sa.Column('disabled_reason',  sa.Enum('expired','refunded','admindisabled',
                                              'fraudsuspected','paymentcanceled','systemerror',
                                              name='disabledreason', create_type=False),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('server_id', 'marzban_username', name='uq_subscriptions_server_username'),
    )
    op.create_index('ix_subscriptions_user_id',         'subscriptions', ['user_id'])
    op.create_index('ix_subscriptions_server_id',       'subscriptions', ['server_id'])
    op.create_index('ix_subscriptions_tariff_id',       'subscriptions', ['tariff_id'])
    op.create_index('ix_subscriptions_expires_at',      'subscriptions', ['expires_at'])
    op.create_index('ix_subscriptions_status',          'subscriptions', ['status'])
    op.create_index('ix_subscriptions_user_status',     'subscriptions', ['user_id', 'status'])
    op.create_index('ix_subscriptions_marzban_username','subscriptions', ['marzban_username'])

    op.create_table(
        'payments',
        sa.Column('id',               sa.BigInteger(), primary_key=True),
        sa.Column('user_id',          sa.BigInteger(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subscription_id',  sa.BigInteger(),
                  sa.ForeignKey('subscriptions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider',         sa.Enum('yookassa', name='paymentprovider',
                                              create_type=False),
                  nullable=False, server_default='yookassa'),
        sa.Column('provider_payment_id', sa.String(128), nullable=True),
        sa.Column('amount',           sa.BigInteger(), nullable=False),
        sa.Column('currency',         sa.String(3),    nullable=False, server_default='RUB'),
        sa.Column('status',           sa.Enum('pending','waitingforcapture','succeeded',
                                              'canceled','refundedpartially','refundedfully',
                                              name='paymentstatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('idempotence_key',  sa.String(128), nullable=False),
        sa.Column('metadata_snapshot',sa.JSON(),      nullable=True),
        sa.Column('paid_at',          sa.DateTime(timezone=True), nullable=True),
        sa.Column('refundable',       sa.Boolean(),   nullable=False, server_default='false'),
        sa.Column('refunded_amount',  sa.BigInteger(),nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('provider_payment_id', name='uq_payments_provider_payment_id'),
        sa.UniqueConstraint('idempotence_key',     name='uq_payments_idempotence_key'),
    )
    op.create_index('ix_payments_user_id',        'payments', ['user_id'])
    op.create_index('ix_payments_subscription_id','payments', ['subscription_id'])
    op.create_index('ix_payments_paid_at',        'payments', ['paid_at'])
    op.create_index('ix_payments_status',         'payments', ['status'])

    op.create_table(
        'refund_requests',
        sa.Column('id',                  sa.BigInteger(), primary_key=True),
        sa.Column('user_id',             sa.BigInteger(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('payment_id',          sa.BigInteger(),
                  sa.ForeignKey('payments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subscription_id',     sa.BigInteger(),
                  sa.ForeignKey('subscriptions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reason',              sa.Text(),    nullable=False),
        sa.Column('status',              sa.Enum('new','inreview','approved','rejected',
                                                 'processed','failed',
                                                 name='refundrequeststatus', create_type=False),
                  nullable=False, server_default='new'),
        sa.Column('admin_comment',       sa.Text(),    nullable=True),
        sa.Column('reviewed_by_admin_id',sa.BigInteger(),
                  sa.ForeignKey('admins.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at',         sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_refund_requests_user_id',             'refund_requests', ['user_id'])
    op.create_index('ix_refund_requests_payment_id',          'refund_requests', ['payment_id'])
    op.create_index('ix_refund_requests_subscription_id',     'refund_requests', ['subscription_id'])
    op.create_index('ix_refund_requests_reviewed_by_admin_id','refund_requests', ['reviewed_by_admin_id'])
    op.create_index('ix_refund_requests_status',              'refund_requests', ['status'])
    op.execute("""
        CREATE UNIQUE INDEX uix_refund_requests_one_pending
        ON refund_requests (subscription_id)
        WHERE status = 'new'
    """)

    op.create_table(
        'refunds',
        sa.Column('id',               sa.BigInteger(), primary_key=True),
        sa.Column('payment_id',       sa.BigInteger(),
                  sa.ForeignKey('payments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('refund_request_id',sa.BigInteger(),
                  sa.ForeignKey('refund_requests.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider',         sa.Enum('yookassa', name='paymentprovider',
                                              create_type=False),
                  nullable=False, server_default='yookassa'),
        sa.Column('provider_refund_id',sa.String(128), nullable=True),
        sa.Column('amount',           sa.BigInteger(), nullable=False),
        sa.Column('currency',         sa.String(3),    nullable=False, server_default='RUB'),
        sa.Column('status',           sa.Enum('pending','succeeded','failed','canceled',
                                              name='refundstatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('raw_payload',      sa.JSON(),       nullable=True),
        sa.Column('completed_at',     sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('provider_refund_id', name='uq_refunds_provider_refund_id'),
    )
    op.create_index('ix_refunds_payment_id',        'refunds', ['payment_id'])
    op.create_index('ix_refunds_refund_request_id', 'refunds', ['refund_request_id'])
    op.create_index('ix_refunds_status',            'refunds', ['status'])

    op.create_table(
        'notifications_log',
        sa.Column('id',              sa.BigInteger(), primary_key=True),
        sa.Column('user_id',         sa.BigInteger(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subscription_id', sa.BigInteger(),
                  sa.ForeignKey('subscriptions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('type',            sa.Enum('subexpires3d','subexpires1d','traffic80',
                                             'traffic95','traffic100','refundprocessed',
                                             'paymentsucceeded',
                                             name='notificationtype', create_type=False),
                  nullable=False),
        sa.Column('payload',         sa.JSON(),  nullable=True),
        sa.Column('sent_at',         sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('delivery_status', sa.Enum('sent','failed',
                                             name='notificationdeliverystatus',
                                             create_type=False),
                  nullable=False, server_default='sent'),
        sa.UniqueConstraint('user_id', 'subscription_id', 'type', name='uq_notifications_dedup'),
    )
    op.create_index('ix_notifications_log_user_id',        'notifications_log', ['user_id'])
    op.create_index('ix_notifications_log_subscription_id','notifications_log', ['subscription_id'])
    op.create_index('ix_notifications_log_type',           'notifications_log', ['type'])

    op.create_table(
        'admin_actions_log',
        sa.Column('id',            sa.BigInteger(), primary_key=True),
        sa.Column('admin_id',      sa.BigInteger(),
                  sa.ForeignKey('admins.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('action',        sa.Enum(
                                       'login','logout','createadmin','updateadmin',
                                       'disableadmin','enableadmin','createserver',
                                       'updateserver','deleteserver','createtariff',
                                       'updatetariff','deletetariff','banuser','unbanuser',
                                       'disablesubscription','enablesubscription',
                                       'approverefund','rejectrefund','processrefund',
                                       name='adminactiontype', create_type=False),
                  nullable=False),
        sa.Column('entity_type',   sa.String(64), nullable=False),
        sa.Column('entity_id',     sa.BigInteger(), nullable=True),
        sa.Column('payload_before',sa.JSON(),     nullable=True),
        sa.Column('payload_after', sa.JSON(),     nullable=True),
        sa.Column('comment',       sa.Text(),     nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_admin_actions_log_admin_id',   'admin_actions_log', ['admin_id'])
    op.create_index('ix_admin_actions_log_action',     'admin_actions_log', ['action'])
    op.create_index('ix_admin_actions_log_entity_type','admin_actions_log', ['entity_type'])
    op.create_index('ix_admin_actions_log_entity_id',  'admin_actions_log', ['entity_id'])


def downgrade() -> None:
    op.drop_table('admin_actions_log')
    op.drop_table('notifications_log')
    op.drop_table('refunds')
    op.drop_table('refund_requests')
    op.drop_table('payments')
    op.drop_table('subscriptions')
    op.drop_table('tariffs')
    op.drop_table('servers')
    op.drop_table('admins')
    op.drop_table('users')

    op.execute('DROP TYPE IF EXISTS adminactiontype')
    op.execute('DROP TYPE IF EXISTS notificationdeliverystatus')
    op.execute('DROP TYPE IF EXISTS notificationtype')
    op.execute('DROP TYPE IF EXISTS refundstatus')
    op.execute('DROP TYPE IF EXISTS refundrequeststatus')
    op.execute('DROP TYPE IF EXISTS paymentstatus')
    op.execute('DROP TYPE IF EXISTS paymentprovider')
    op.execute('DROP TYPE IF EXISTS disabledreason')
    op.execute('DROP TYPE IF EXISTS subscriptionstatus')
