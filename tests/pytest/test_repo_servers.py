from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from config import get_crypto_key
from database.repo.servers import ServerRepo
from tests.pytest.factories import make_server
from utils.crypto import decrypt_secret, encrypt_secret

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_get_active_returns_only_active_ordered_by_sort_order(
    db_session: AsyncSession,
) -> None:
    repo = ServerRepo(db_session)

    s1 = make_server(is_active=True, sort_order=200)
    s2 = make_server(is_active=True, sort_order=100)
    s3 = make_server(is_active=False, sort_order=50)
    db_session.add_all([s1, s2, s3])
    await db_session.flush()

    result = await repo.get_active()

    ids = [s.id for s in result]
    assert s3.id not in ids
    assert ids.index(s2.id) < ids.index(s1.id)


@pytest.mark.asyncio
async def test_get_by_id_active_found(db_session: AsyncSession) -> None:
    repo = ServerRepo(db_session)
    server = make_server(is_active=True)
    db_session.add(server)
    await db_session.flush()

    result = await repo.get_by_id_active(server.id)

    assert result is not None
    assert result.id == server.id


@pytest.mark.asyncio
async def test_get_by_id_active_inactive_returns_none(db_session: AsyncSession) -> None:
    repo = ServerRepo(db_session)
    server = make_server(is_active=False)
    db_session.add(server)
    await db_session.flush()

    result = await repo.get_by_id_active(server.id)

    assert result is None


@pytest.mark.asyncio
async def test_get_by_id_active_missing_returns_none(db_session: AsyncSession) -> None:
    repo = ServerRepo(db_session)

    result = await repo.get_by_id_active(999999)

    assert result is None


@pytest.mark.asyncio
async def test_set_active_toggles_flag(db_session: AsyncSession) -> None:
    repo = ServerRepo(db_session)
    server = make_server(is_active=True)
    db_session.add(server)
    await db_session.flush()

    updated = await repo.set_active(server, active=False)

    assert updated.is_active is False


@pytest.mark.asyncio
async def test_get_server_secrets_not_found_returns_none(
    db_session: AsyncSession,
) -> None:
    repo = ServerRepo(db_session)

    result = await repo.get_server_secrets(999999)

    assert result is None


@pytest.mark.asyncio
async def test_get_server_secrets_no_token_returns_none_plain(
    db_session: AsyncSession,
) -> None:
    repo = ServerRepo(db_session)
    server = make_server(metrics_token=None)
    db_session.add(server)
    await db_session.flush()

    result = await repo.get_server_secrets(server.id)

    assert result is not None
    assert result.server_id == server.id
    assert result.metrics_token is None


@pytest.mark.asyncio
async def test_get_server_secrets_decrypts_token(db_session: AsyncSession) -> None:
    repo = ServerRepo(db_session)
    key = get_crypto_key()
    encrypted = encrypt_secret("real-metrics-token", key)
    server = make_server(metrics_token=encrypted)
    db_session.add(server)
    await db_session.flush()

    result = await repo.get_server_secrets(server.id)

    assert result is not None
    assert result.metrics_token == "real-metrics-token"
    assert decrypt_secret(server.metrics_token, key) == "real-metrics-token"


@pytest.mark.asyncio
async def test_get_server_secrets_empty_decrypted_value_becomes_none(
    db_session: AsyncSession,
) -> None:
    repo = ServerRepo(db_session)
    server = make_server(metrics_token="some-non-empty-ciphertext")
    db_session.add(server)
    await db_session.flush()

    with patch("database.repo.servers.decrypt_secret", return_value=""):
        result = await repo.get_server_secrets(server.id)

    assert result is not None
    assert result.metrics_token is None


@pytest.mark.asyncio
async def test_set_server_tokens_encrypts_and_stores(db_session: AsyncSession) -> None:
    repo = ServerRepo(db_session)
    server = make_server(metrics_token=None)
    db_session.add(server)
    await db_session.flush()

    await repo.set_server_tokens(server.id, "brand-new-token")

    await db_session.refresh(server)
    assert server.metrics_token is not None
    assert server.metrics_token != "brand-new-token"
    decrypted = decrypt_secret(server.metrics_token, get_crypto_key())
    assert decrypted == "brand-new-token"


@pytest.mark.asyncio
async def test_set_server_tokens_none_clears_token(db_session: AsyncSession) -> None:
    repo = ServerRepo(db_session)
    key = get_crypto_key()
    server = make_server(metrics_token=encrypt_secret("old-token", key))
    db_session.add(server)
    await db_session.flush()

    await repo.set_server_tokens(server.id, None)

    await db_session.refresh(server)
    assert server.metrics_token is None
