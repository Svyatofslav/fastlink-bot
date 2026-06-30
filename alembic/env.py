from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv  # NEW

from config import get_settings  # вместо прямого import settings
from database.base import Base
import database.models  # noqa: F401

# ─── Load environment (.env + optional .env.local) ─────────
# .env.local переопределяет значения из .env, если существует.
load_dotenv(".env", override=False)
load_dotenv(".env.local", override=True)

# Пересобираем Settings с учётом загруженных переменных.
get_settings.cache_clear()
settings = get_settings()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic всегда использует sync-DSN из Settings.
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
