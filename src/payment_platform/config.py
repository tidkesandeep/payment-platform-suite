from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAYMENTS_")

    database_url: str = "postgresql://payments:payments@127.0.0.1:5432/payments"
    redis_url: str = "redis://127.0.0.1:6379/0"
    api_key: str = "sk_test_demo"
    api_key_id: str = "ak_demo"
    lease_seconds: int = 30
    intent_fail_closed: bool = True
    body_max_bytes: int = 65536
    max_amount_minor: int = 5_000_000
    max_attempts_1h: int = 20
    max_attempts_24h: int = 80
    max_approved_amount_minor_24h: int = 2_000_000
    allowed_currencies: str = "USD"
    kafka_bootstrap: str = "127.0.0.1:19092"
    publisher_poll_seconds: float = 0.25
    score_timeout_ms: int = 20
    investigator_rate_limit_per_minute: int = 60


settings = Settings()
