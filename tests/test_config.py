from settings_schema import Settings


def build_settings(**overrides) -> Settings:
    data = {
        "APP_ENV": "development",
        "APP_DEBUG": False,
        "LOG_LEVEL": "INFO",
        "BOT_TOKEN": "test-token",
        "WEBHOOK_BASE_URL": "https://example.com",
        "WEBHOOK_PATH": "/webhook/test",
        "WEBHOOK_SECRET": "secret",
        "POSTGRES_DB": "fastlink",
        "POSTGRES_USER": "fastlink",
        "POSTGRES_PASSWORD": "password",
        "REDIS_PASSWORD": "redispass",
        "REDIS_HOST": "redis",
        "REDIS_PORT": 6379,
        "REDIS_DB": 0,
        "REDIS_FSM_DB": 1,
        "REDIS_CACHE_DB": 2,
        "REDIS_RATE_LIMIT_DB": 3,
        "REDIS_PAYMENT_DB": 4,
        "REDIS_MARZBAN_TOKEN_DB": 5,
        "DATABASE_URL": "postgresql+asyncpg://fastlink:password@postgres:5432/fastlink",
        "DATABASE_URL_SYNC": "postgresql://fastlink:password@postgres:5432/fastlink",
        "REDIS_URL": "redis://:redispass@redis:6379/0",
        "REDIS_URL_FSM": "redis://:redispass@redis:6379/1",
        "REDIS_URL_CACHE": "redis://:redispass@redis:6379/2",
        "REDIS_URL_RATE_LIMIT": "redis://:redispass@redis:6379/3",
        "REDIS_URL_PAYMENT": "redis://:redispass@redis:6379/4",
        "REDIS_URL_MARZBAN_TOKEN": "redis://:redispass@redis:6379/5",
        "MARZBAN_API_BASE": "http://host.docker.internal:8000/api",
        "MARZBAN_USERNAME": "admin",
        "MARZBAN_PASSWORD": "password",
        "METRICS_URL": "https://example.com/metrics",
        "METRICS_TOKEN": "metrics-token",
        "OWNER_TELEGRAM_ID": 123456789,
    }
    data.update(overrides)
    return Settings(**data)


def test_settings_computed_fields():
    settings = build_settings(
        WEBHOOK_BASE_URL="https://example.com/",
        WEBHOOK_PATH="/telegram/webhook",
        HEALTHCHECK_PATH="health",
    )

    assert settings.webhook_url == "https://example.com/telegram/webhook"
    assert settings.healthcheck_url_path == "/health"


def test_settings_defaults():
    settings = build_settings()

    assert settings.bot_parse_mode == "HTML"
    assert settings.http_port == 8080
    assert settings.use_webhook is True


def test_is_production_flag():
    settings = build_settings(APP_ENV="production")

    assert settings.is_production is True
