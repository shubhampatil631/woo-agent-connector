from enum import StrEnum

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthType(StrEnum):
    API_KEY = "api_key"
    OAUTH = "oauth"


class PIIMode(StrEnum):
    REDACTED = "redacted"
    FULL = "full"


class Settings(BaseSettings):
    """Application and connector settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="WOO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    store_url: HttpUrl = Field(
        default=HttpUrl("http://localhost:8080"),
        description="Base URL of the WooCommerce store (e.g., https://store.example.com)",
    )
    consumer_key: str = Field(
        default="",
        description="WooCommerce REST API Consumer Key (ck_...)",
    )
    consumer_secret: str = Field(
        default="",
        description="WooCommerce REST API Consumer Secret (cs_...)",
    )
    auth_type: AuthType = Field(
        default=AuthType.API_KEY,
        description="Authentication strategy: api_key or oauth",
    )
    pii_mode: PIIMode = Field(
        default=PIIMode.REDACTED,
        description="PII filtering mode: redacted (default) or full",
    )
    max_page_size: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum allowed items per page for list endpoints",
    )
    request_timeout: float = Field(
        default=15.0,
        gt=0,
        description="HTTP request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts on rate limits or transient errors",
    )
    backoff_factor: float = Field(
        default=1.5,
        gt=0,
        description="Exponential backoff multiplier for retries",
    )


settings = Settings()
