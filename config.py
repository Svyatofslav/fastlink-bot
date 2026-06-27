from functools import lru_cache

from settings_schema import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
