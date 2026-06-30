from functools import lru_cache
from pathlib import Path

from settings_schema import Settings
from utils.crypto import derive_key_from_env

DEPLOY_COMMIT_SHORT_PATH = Path("/app/.deploy-commit-short")


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_crypto_key() -> bytes:
    """
    Return the AES-256 master key for application-level encryption.

    The key is derived once from FASTLINK_CRYPTO_MASTER_KEY (hex-encoded)
    and cached for the lifetime of the process.
    """
    settings = get_settings()
    raw = settings.fastlink_crypto_master_key.get_secret_value()
    return derive_key_from_env(raw)


def get_deploy_commit_short() -> str:
    try:
        value = DEPLOY_COMMIT_SHORT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value or "unknown"
