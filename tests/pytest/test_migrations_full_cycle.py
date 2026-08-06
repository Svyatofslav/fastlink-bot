from __future__ import annotations

import psycopg2
import pytest
from alembic.config import Config

from alembic import command
from config import get_settings


def _to_psycopg2_dsn(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture
def isolated_migration_db():
    settings = get_settings()
    base_url = _to_psycopg2_dsn(settings.database_url_sync).rsplit("/", 1)[0]
    admin_url = f"{base_url}/postgres"
    db_name = "fastlink_migrations_test"

    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
        cur.execute(f"CREATE DATABASE {db_name}")
    conn.close()

    yield f"{base_url}/{db_name}"

    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
        )
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    conn.close()


def test_full_downgrade_upgrade_cycle(isolated_migration_db):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", isolated_migration_db)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
