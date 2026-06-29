from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerSecrets:
    """
    Plaintext secrets for a single server.

    api_token / metrics_token are decrypted values.
    If a token is absent in DB, the corresponding field is None.
    """

    server_id: int
    api_token: str | None
    metrics_token: str | None
