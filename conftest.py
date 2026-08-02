from __future__ import annotations

import atexit
import os
import sys
import uuid
from pathlib import Path

import psycopg2
from alembic.config import Config as AlembicConfig
from dotenv import load_dotenv
from psycopg2 import sql

from alembic import command
from config import get_crypto_key, get_settings

# 1. Настроить sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2. Загрузить .env и .env.local ДО импортов тестовых модулей
env_file = Path(".env")
env_local_file = Path(".env.local")

if env_file.exists():
    load_dotenv(".env", override=False)
if env_local_file.exists():
    load_dotenv(".env.local", override=True)

# 3. Сбросить кэш настроек, чтобы Settings() пересоздался с уже загруженными env
get_settings.cache_clear()
get_crypto_key.cache_clear()

# 4. Изолированная тестовая БД: создаётся один раз перед всей сессией pytest,
#    гарантированно удаляется после завершения процесса (успех/фейл/Ctrl+C).
#
# Без этого блока все тесты (включая race-тесты, которым необходим реальный
# commit, а не rollback) писали бы прямо в рабочую БД бота (POSTGRES_DB=fastlink
# из .env), потому что create_test_engine() строит URL через get_settings(),
# а тот в свою очередь читает POSTGRES_DB из окружения. Подставляя сюда имя
# одноразовой БД до первого вызова create_test_engine(), мы разворачиваем
# ВСЕ тесты на изолированную БД без единой правки в самих тестах.

_test_db_name = (
    f"{os.environ.get('POSTGRES_DB', 'fastlink')}_test_{uuid.uuid4().hex[:8]}"
)

_maintenance_dsn = (
    f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}/postgres"
)


def _create_test_database() -> None:
    conn = psycopg2.connect(_maintenance_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(_test_db_name)
                )
            )
            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(_test_db_name))
            )
    finally:
        conn.close()


def _drop_test_database() -> None:
    conn = psycopg2.connect(_maintenance_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            # Обрываем возможные "зависшие" подключения к тестовой БД
            # (например, если pytest был прерван Ctrl+C и пул не закрылся),
            # иначе DROP DATABASE упадёт с "database is being accessed by other users".
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_test_db_name,),
            )
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(_test_db_name)
                )
            )
    finally:
        conn.close()


_create_test_database()
os.environ["POSTGRES_DB"] = _test_db_name

# Перечитываем Settings с новым POSTGRES_DB, чтобы database_url/database_url_sync
# указывали на только что созданную изолированную БД.
get_settings.cache_clear()
get_crypto_key.cache_clear()

# 5. Прогоняем миграции Alembic на изолированной БД (аналогично тому,
#    как это уже делает test_migrations_full_cycle.py для своей отдельной БД).
_alembic_cfg = AlembicConfig(str(ROOT / "alembic.ini"))
_alembic_cfg.set_main_option("sqlalchemy.url", get_settings().database_url_sync)
command.upgrade(_alembic_cfg, "head")

# 6. Гарантированное удаление тестовой БД после завершения процесса pytest,
#    независимо от того, прошли тесты, упали или процесс был прерван.
atexit.register(_drop_test_database)
