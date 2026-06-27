from functools import lru_cache
from pathlib import Path

from settings_schema import Settings

DEPLOY_COMMIT_SHORT_PATH = Path("/opt/fastlink-bot/.deploy-commit-short")


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_deploy_commit_short() -> str:
    try:
        value = DEPLOY_COMMIT_SHORT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value or "unknown"


settings = get_settings()
deploy_commit_short = get_deploy_commit_short()
