from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
            select(Server)
            .where(Server.is_active == True)  # noqa: E712
            .order_by(Server.sort_order),
        )
        return list(result.scalars().all())

    async def get_by_id_active(self, server_id: int) -> Server | None:
        result = await self.session.execute(
            select(Server).where(
                Server.id == server_id,
                Server.is_active == True,  # noqa: E712
            ),
        )
        return result.scalar_one_or_none()

    async def set_active(self, server: Server, *, active: bool) -> Server:
        return await self.update(server, is_active=active)

    async def get_server_secrets(self, server_id: int) -> ServerSecrets | None:
        """
        Вернуть расшифрованные API/metrics токены для сервера.

        Если сервер не найден, вернуть None.
        """
        server = await self.get_by_id(server_id)
        if server is None:
            return None

        api_token_plain: str | None = None
        metrics_token_plain: str | None = None

        if server.api_token:
            api_token_plain = decrypt_secret(server.api_token, self._crypto_key)
            if api_token_plain == "":
                api_token_plain = None

        if server.metrics_token:
            metrics_token_plain = decrypt_secret(
                server.metrics_token,
                self._crypto_key,
            )
            if metrics_token_plain == "":
                metrics_token_plain = None

        return ServerSecrets(
            server_id=server.id,
            api_token=api_token_plain,
            metrics_token=metrics_token_plain,
        )

    async def set_server_tokens(
        self,
        server_id: int,
        api_token: str | None,
        metrics_token: str | None,
    ) -> None:
        """
        Зашифровать и сохранить API/metrics токены для сервера.

        None → очистить соответствующий токен (NULL в БД).
        """
        api_token_enc: str | None = None
        metrics_token_enc: str | None = None

        if api_token is not None:
            api_token_enc = encrypt_secret(api_token, self._crypto_key)

        if metrics_token is not None:
            metrics_token_enc = encrypt_secret(metrics_token, self._crypto_key)

        stmt = (
            update(Server)
            .where(Server.id == server_id)
            .values(api_token=api_token_enc, metrics_token=metrics_token_enc)
        )
        await self.session.execute(stmt)
        await self.session.flush()
