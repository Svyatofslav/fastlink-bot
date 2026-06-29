from __future__ import annotations

from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20240629_mark_servers_tokens_encrypted"
down_revision: Union[str, None] = "522f84617ca9"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "COMMENT ON COLUMN servers.api_token IS "
        "'Encrypted Marzban API token (AES-256-GCM, base64(nonce+cipher+tag))';",
    )
    op.execute(
        "COMMENT ON COLUMN servers.metrics_token IS "
        "'Encrypted metrics bearer token (AES-256-GCM, base64(nonce+cipher+tag))';",
    )
    # Опционально — если хочешь обнулить старые открытые токены:
    # op.execute("UPDATE servers SET api_token = NULL, metrics_token = NULL;")


def downgrade() -> None:
    op.execute("COMMENT ON COLUMN servers.api_token IS NULL;")
    op.execute("COMMENT ON COLUMN servers.metrics_token IS NULL;")
