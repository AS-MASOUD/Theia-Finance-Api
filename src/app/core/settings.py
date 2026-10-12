from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.app.core.exceptions import InvalidOperationException


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core App
    PROJECT_NAME: str = "Personal Finance Command Center"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "development-secret-key-at-least-32-chars-long"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/personal_fc"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Market Data & AI
    MARKET_DATA_PROVIDER: str = "mock"  # brs, mock
    BRS_API_KEY: str = ""
    BRS_COMMODITY_URL: str = "https://api.brsapi.ir/Market/Commodity.php"
    BRS_CRYPTO_URL: str = "https://api.brsapi.ir/Market/Cryptocurrency.php"
    BRS_GOLD_CURRENCY_URL: str = "https://api.brsapi.ir/Market/Gold_Currency.php"
    MARKET_SYNC_INTERVAL_HOURS: float = 4.8  # 5 times a day (24 / 5 = 4.8 hours = 17,280 seconds)
    ENABLE_MARKET_SYNC_TASK: bool = True
    AI_PROVIDER: str = "mock"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Base financial defaults
    DEFAULT_BASE_CURRENCY: str = "TOMAN"

    # Identity, Password & Brute-Force Lockout Policies
    MAX_FAILED_ACCESS_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    ALLOWED_LOCKOUT_FOR_NEW_USERS: bool = True
    MIN_PASSWORD_LENGTH: int = 8

    # Communications & OTP (Supports Iranian SMS & Email Providers)
    SMS_PROVIDER: str = "mock"  # mock, kavenegar, farazsms
    KAVENEGAR_API_KEY: str = ""
    KAVENEGAR_SENDER: str = ""
    FARAZSMS_API_KEY: str = ""
    FARAZSMS_SENDER: str = ""
    FARAZSMS_PATTERN_CODE: str = ""

    EMAIL_PROVIDER: str = "mock"  # mock, smtp
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@personal-fc.local"
    SMTP_USE_TLS: bool = True

    OTP_EXPIRE_SECONDS: int = 180
    OTP_COOLDOWN_SECONDS: int = 120
    OTP_DIGITS: int = 5

    # Asset Volatility Alert Threshold (%)
    ASSET_ALERT_THRESHOLD_PERCENT: float = 4.0

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Fail fast in production if production secrets or connection strings are missing or default."""
        if self.ENVIRONMENT.lower() == "production":
            insecure_secret_defaults = (
                "development-secret-key-at-least-32-chars-long",
                "insecure-default-change-in-production-env",
                "change-this-in-production-to-a-secure-random-string",
                "development-only-secret-key-must-be-changed-in-production-32-chars-min",
            )
            if not self.SECRET_KEY or self.SECRET_KEY in insecure_secret_defaults or len(self.SECRET_KEY) < 32:
                raise InvalidOperationException(
                    "Production configuration error: SECRET_KEY must be set to a secure, "
                    "cryptographically random string with at least 32 characters in production."
                )

            if not self.DATABASE_URL or "admin:admin" in self.DATABASE_URL or "postgres:postgres" in self.DATABASE_URL:
                raise InvalidOperationException(
                    "Production configuration error: Default database credentials (admin:admin or postgres:postgres) "
                    "are prohibited in production. A secure DATABASE_URL must be configured."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

