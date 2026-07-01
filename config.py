from __future__ import annotations

from functools import lru_cache

from settings_schema import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Глобальный объект настроек для простых импортов
settings = get_settings()


@lru_cache
def get_crypto_key() -> bytes:
    # использование settings.fastlink_crypto_master_key
    key_hex = settings.fastlink_crypto_master_key.get_secret_value()
    return bytes.fromhex(key_hex)
