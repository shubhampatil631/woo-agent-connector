from enum import StrEnum
from typing import Self

from pydantic import AliasChoices, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(ValueError):
    """Raised when required connector configuration is invalid or missing."""


class PIIMode(StrEnum):
    REDACTED = "redacted"
    FULL = "full"


class AuthType(StrEnum):
    API_KEY = "api_key"
    OAUTH = "oauth"


def mask_secret(value: str | None, prefix_len: int = 4) -> str:
    """Mask a secret string for safe logging and representations."""
    if not value:
        return "<not-set>"
    if len(value) <= prefix_len:
        return "***"
    return f"{value[:prefix_len]}...[REDACTED]"


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    base_url: HttpUrl = Field(
        default=HttpUrl("http://localhost:8080"),
        validation_alias=AliasChoices(
            "WOO_BASE_URL", "WOO_STORE_URL", "BASE_URL", "base_url"
        ),
        description="Base URL of the WooCommerce store (e.g., http://localhost:8080 or https://store.com)",
    )
    consumer_key: str = Field(
        default="",
        validation_alias=AliasChoices("WOO_CONSUMER_KEY", "CONSUMER_KEY", "consumer_key"),
        description="WooCommerce REST API Consumer Key (ck_...)",
    )
    consumer_secret: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WOO_CONSUMER_SECRET", "CONSUMER_SECRET", "consumer_secret"
        ),
        description="WooCommerce REST API Consumer Secret (cs_...)",
    )
    auth_type: AuthType = Field(
        default=AuthType.API_KEY,
        validation_alias=AliasChoices("WOO_AUTH_TYPE", "AUTH_TYPE", "auth_type"),
        description="Authentication mode: api_key or oauth",
    )
    pii_mode: PIIMode = Field(
        default=PIIMode.REDACTED,
        validation_alias=AliasChoices("PII_MODE", "WOO_PII_MODE", "pii_mode"),
        description="PII sanitization mode: redacted or full",
    )
    max_page_size: int = Field(
        default=50,
        ge=1,
        le=100,
        validation_alias=AliasChoices("MAX_PAGE_SIZE", "WOO_MAX_PAGE_SIZE", "max_page_size"),
        description="Maximum allowed items per page for list queries",
    )
    rate_limit_rps: float = Field(
        default=5.0,
        gt=0,
        validation_alias=AliasChoices("RATE_LIMIT_RPS", "WOO_RATE_LIMIT_RPS", "rate_limit_rps"),
        description="Client-side rate limit in requests per second",
    )
    request_timeout: float = Field(
        default=15.0,
        gt=0,
        validation_alias=AliasChoices(
            "REQUEST_TIMEOUT", "WOO_REQUEST_TIMEOUT", "request_timeout"
        ),
        description="HTTP request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        validation_alias=AliasChoices("MAX_RETRIES", "WOO_MAX_RETRIES", "max_retries"),
        description="Maximum retry attempts for rate limits and transient errors",
    )
    backoff_factor: float = Field(
        default=1.5,
        gt=0,
        validation_alias=AliasChoices(
            "BACKOFF_FACTOR", "WOO_BACKOFF_FACTOR", "backoff_factor"
        ),
        description="Exponential backoff multiplier for retries",
    )
    connector_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CONNECTOR_API_KEY", "WOO_CONNECTOR_API_KEY", "connector_api_key"
        ),
        description="Optional API key securing the MCP connector HTTP endpoint",
    )

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url_string(cls, v: str | HttpUrl) -> str | HttpUrl:
        if isinstance(v, str):
            v_clean = v.strip().rstrip("/")
            if not v_clean.startswith(("http://", "https://")):
                raise ConfigurationError(
                    f"Invalid WOO_BASE_URL '{v}': must start with http:// or https://"
                )
            return v_clean
        return v

    def validate_required(self) -> Self:
        """Enforce that required credentials are present for active API operations."""
        missing = []
        if not str(self.base_url).strip():
            missing.append("WOO_BASE_URL")
        if not self.consumer_key.strip():
            missing.append("WOO_CONSUMER_KEY")
        if not self.consumer_secret.strip():
            missing.append("WOO_CONSUMER_SECRET")

        if missing:
            raise ConfigurationError(
                f"Missing required WooCommerce configuration: {', '.join(missing)}. "
                "Please configure them in your environment or .env file."
            )
        return self

    def __repr__(self) -> str:
        return (
            f"Settings("
            f"base_url={str(self.base_url)!r}, "
            f"consumer_key={mask_secret(self.consumer_key)!r}, "
            f"consumer_secret={mask_secret(self.consumer_secret)!r}, "
            f"auth_type={self.auth_type.value!r}, "
            f"pii_mode={self.pii_mode.value!r}, "
            f"max_page_size={self.max_page_size}, "
            f"rate_limit_rps={self.rate_limit_rps}, "
            f"request_timeout={self.request_timeout}, "
            f"max_retries={self.max_retries}, "
            f"backoff_factor={self.backoff_factor}, "
            f"connector_api_key={mask_secret(self.connector_api_key)!r}"
            f")"
        )

    def __str__(self) -> str:
        return self.__repr__()


def get_settings(strict: bool = False, **kwargs) -> Settings:
    """Factory helper to obtain a settings instance with optional strict validation."""
    s = Settings(**kwargs)
    if strict:
        s.validate_required()
    return s


settings = Settings()
