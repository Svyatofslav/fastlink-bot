from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    app_env: Literal["development", "production", "test"] = Field(alias="APP_ENV")
    app_debug: bool = Field(alias="APP_DEBUG")
    log_level: str = Field(alias="LOG_LEVEL")

    bot_token: str = Field(alias="BOT_TOKEN")
    bot_parse_mode: str = Field(default="HTML", alias="BOT_PARSE_MODE")

    webhook_base_url: str = Field(alias="WEBHOOK_BASE_URL")
    webhook_path: str = Field(alias="WEBHOOK_PATH")
    webhook_secret: str = Field(alias="WEBHOOK_SECRET")
    healthcheck_path: str = Field(default="/health", alias="HEALTHCHECK_PATH")
    http_host: str = Field(default="0.0.0.0", alias="HTTP_HOST")
    http_port: int = Field(default=8080, alias="HTTP_PORT")
    use_webhook: bool = Field(default=True, alias="USE_WEBHOOK")
    skip_webhook_registration: bool = Field(
        default=False, alias="SKIP_WEBHOOK_REGISTRATION"
    )

    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")

    redis_password: str = Field(alias="REDIS_PASSWORD")
    redis_host: str = Field(alias="REDIS_HOST")
    redis_port: int = Field(alias="REDIS_PORT")
    redis_db: int = Field(alias="REDIS_DB")
    redis_fsm_db: int = Field(alias="REDIS_FSM_DB")
    redis_cache_db: int = Field(alias="REDIS_CACHE_DB")
    redis_rate_limit_db: int = Field(alias="REDIS_RATE_LIMIT_DB")
    redis_payment_db: int = Field(alias="REDIS_PAYMENT_DB")
    redis_marzban_token_db: int = Field(alias="REDIS_MARZBAN_TOKEN_DB")

    database_url: str = Field(alias="DATABASE_URL")
    database_url_sync: str = Field(alias="DATABASE_URL_SYNC")

    redis_url: str = Field(alias="REDIS_URL")
    redis_url_fsm: str = Field(alias="REDIS_URL_FSM")
    redis_url_cache: str = Field(alias="REDIS_URL_CACHE")
    redis_url_rate_limit: str = Field(alias="REDIS_URL_RATE_LIMIT")
    redis_url_payment: str = Field(alias="REDIS_URL_PAYMENT")
    redis_url_marzban_token: str = Field(alias="REDIS_URL_MARZBAN_TOKEN")

    marzban_api_base: str = Field(alias="MARZBAN_API_BASE")
    marzban_username: str = Field(alias="MARZBAN_USERNAME")
    marzban_password: str = Field(alias="MARZBAN_PASSWORD")
    marzban_timeout_seconds: int = Field(default=10, alias="MARZBAN_TIMEOUT_SECONDS")

    metrics_url: str = Field(alias="METRICS_URL")
    metrics_token: str = Field(alias="METRICS_TOKEN")

    owner_telegram_id: int = Field(alias="OWNER_TELEGRAM_ID")
    admin_session_ttl_seconds: int = Field(
        default=28800, alias="ADMIN_SESSION_TTL_SECONDS"
    )

    default_language: str = Field(default="ru", alias="DEFAULT_LANGUAGE")
    feature_i18n_enabled: bool = Field(default=False, alias="FEATURE_I18N_ENABLED")

    yookassa_shop_id: str = Field(default="", alias="YOOKASSA_SHOP_ID")
    yookassa_secret_key: str = Field(default="", alias="YOOKASSA_SECRET_KEY")

    feature_admin_enabled: bool = Field(default=True, alias="FEATURE_ADMIN_ENABLED")
    feature_payments_enabled: bool = Field(
        default=False, alias="FEATURE_PAYMENTS_ENABLED"
    )
    feature_refunds_enabled: bool = Field(
        default=False, alias="FEATURE_REFUNDS_ENABLED"
    )

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    marzban_token_ttl_seconds: int = 23 * 60 * 60

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @computed_field
    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"

    @computed_field
    @property
    def healthcheck_url_path(self) -> str:
        if self.healthcheck_path.startswith("/"):
            return self.healthcheck_path
        return f"/{self.healthcheck_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
