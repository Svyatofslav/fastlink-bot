from functools import lru_cache
from pathlib import Path

from settings_schema import Settings

DEPLOY_COMMIT_SHORT_PATH = Path("/app/.deploy-commit-short")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_deploy_commit_short() -> str:
    try:
        value = DEPLOY_COMMIT_SHORT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value or "unknown"


settings = get_settings()
