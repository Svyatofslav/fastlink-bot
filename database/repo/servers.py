from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from config import get_crypto_key
from database.models import Server
from database.repo.base import BaseRepo
from database.repo.dto import ServerSecrets
from utils.crypto import decrypt_secret, encrypt_secret


class ServerRepo(BaseRepo[Server]):
    model = Server

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._crypto_key = get_crypto_key()

    async def get_active(self) -> list[Server]:
        result = await self.session.execute(
            select(Server).where(Server.is_active == True).order_by(Server.sort_order),
        )
        return list(result.scalars().all())

    async def get_by_id_active(self, server_id: int) -> Server | None:
        result = await self.session.execute(
            select(Server).where(
                Server.id == server_id,
                Server.is_active == True,
            ),
        )
        return result.scalar_one_or_none()

    async def set_active(self, server: Server, *, active: bool) -> Server:
        return await self.update(server, is_active=active)

    async def get_server_secrets(self, server_id: int) -> ServerSecrets | None:
        server = await self.get_by_id(server_id)
        if server is None:
            return None

        metrics_token_plain: str | None = None
        if server.metrics_token:
            metrics_token_plain = decrypt_secret(server.metrics_token, self._crypto_key)
            if not metrics_token_plain:
                metrics_token_plain = None

        return ServerSecrets(server_id=server.id, metrics_token=metrics_token_plain)

    async def set_server_tokens(
        self, server_id: int, metrics_token: str | None
    ) -> None:
        metrics_token_enc: str | None = None
        if metrics_token is not None:
            metrics_token_enc = encrypt_secret(metrics_token, self._crypto_key)

        stmt = (
            update(Server)
            .where(Server.id == server_id)
            .values(metrics_token=metrics_token_enc)
        )
        await self.session.execute(stmt)
        await self.session.flush()
