"""rebuild admin_action_type and notification_type enums with correct casing

Revision ID: 1adb3f0f1e8b
Revises: 8cd4052a0f89
Create Date: 2026-09-05 11:17:34.141154

"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1adb3f0f1e8b'
down_revision: Union[str, None] = '8cd4052a0f89'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Таблицы admin_actions_log и notifications_log гарантированно пустые
    # (pre-launch, admin/support-flow ещё не реализован, донаты не
    # отправлялись) — поэтому вместо ALTER TYPE ... ADD VALUE (что оставило
    # бы orphaned строчные лейблы навсегда, как это уже произошло с
    # notification_type.donation_succeeded в f67b6c398276/f798517c235b)
    # пересоздаём оба enum-типа с нуля, содержащими только корректные
    # значения. Такой подход возможен только потому, что таблицы пусты —
    # на заполненных таблицах потребовался бы иной путь (ADD VALUE +
    # бэкфилл существующих строк на новые значения).

    # --- admin_action_type: убираем orphaned строчные support-ticket значения ---
    op.execute("""
        CREATE TYPE admin_action_type_new AS ENUM (
            'LOGIN', 'LOGOUT', 'CREATE_ADMIN', 'UPDATE_ADMIN', 'DISABLE_ADMIN',
            'ENABLE_ADMIN', 'CREATE_SERVER', 'UPDATE_SERVER', 'DELETE_SERVER',
            'CREATE_TARIFF', 'UPDATE_TARIFF', 'DELETE_TARIFF', 'BAN_USER',
            'UNBAN_USER', 'DISABLE_SUBSCRIPTION', 'ENABLE_SUBSCRIPTION',
            'APPROVE_REFUND', 'REJECT_REFUND', 'PROCESS_REFUND',
            'ASSIGN_SUPPORT_TICKET', 'REPLY_SUPPORT_TICKET', 'CLOSE_SUPPORT_TICKET'
        )
    """)
    op.execute(
        "ALTER TABLE admin_actions_log "
        "ALTER COLUMN action TYPE admin_action_type_new "
        "USING action::text::admin_action_type_new"
    )
    op.execute("DROP TYPE admin_action_type")
    op.execute("ALTER TYPE admin_action_type_new RENAME TO admin_action_type")

    # --- notification_type: убираем orphaned строчный donation_succeeded ---
    op.execute("""
        CREATE TYPE notification_type_new AS ENUM (
            'SUB_EXPIRES_3D', 'SUB_EXPIRES_1D', 'TRAFFIC_80', 'TRAFFIC_95',
            'TRAFFIC_100', 'REFUND_PROCESSED', 'PAYMENT_SUCCEEDED',
            'DONATION_SUCCEEDED'
        )
    """)
    op.execute(
        "ALTER TABLE notifications_log "
        "ALTER COLUMN type TYPE notification_type_new "
        "USING type::text::notification_type_new"
    )
    op.execute("DROP TYPE notification_type")
    op.execute("ALTER TYPE notification_type_new RENAME TO notification_type")


def downgrade() -> None:
    # Восстановление orphaned-лейблов бессмысленно — они существовали
    # только как след ранее исправленных ошибок в миграциях и никогда
    # не использовались приложением. Откат не предусмотрен, как и для
    # аналогичных enum-миграций в этом проекте (f67b6c398276/f798517c235b).
    pass
