from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from settings_schema import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Глобальный объект настроек для простых импортов
settings = get_settings()


@lru_cache
def get_crypto_key() -> bytes:
    key_hex = settings.fastlink_crypto_master_key.get_secret_value()
    return bytes.fromhex(key_hex)


def get_deploy_commit_short() -> str:
    value = os.getenv("DEPLOY_COMMIT_SHORT")
    if value:
        return value.strip()
    try:
        return Path(".deploy-commit-short").read_text().strip()
    except FileNotFoundError:
        return "unknown"
