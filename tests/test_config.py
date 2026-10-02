"""Tests for configuration parsing, validation, and secret masking."""

import pytest
from pydantic import ValidationError

from woo_connector.config import (
    AuthType,
    ConfigurationError,
    PIIMode,
    Settings,
    get_settings,
    mask_secret,
)


def test_default_settings():
    s = Settings(
        consumer_key="ck_test123",
        consumer_secret="cs_test456",
    )
    assert str(s.base_url) == "http://localhost:8080/"
    assert s.auth_type == AuthType.API_KEY
    assert s.pii_mode == PIIMode.REDACTED
    assert s.max_page_size == 50
    assert s.rate_limit_rps == 5.0
    assert s.request_timeout == 15.0
    assert s.max_retries == 3
    assert s.connector_api_key is None


def test_custom_settings_and_aliases(monkeypatch):
    monkeypatch.setenv("WOO_BASE_URL", "https://store.example.com")
    monkeypatch.setenv("WOO_CONSUMER_KEY", "ck_prod_key")
    monkeypatch.setenv("WOO_CONSUMER_SECRET", "cs_prod_secret")
    monkeypatch.setenv("PII_MODE", "full")
    monkeypatch.setenv("MAX_PAGE_SIZE", "75")
    monkeypatch.setenv("RATE_LIMIT_RPS", "10")
    monkeypatch.setenv("REQUEST_TIMEOUT", "30.0")
    monkeypatch.setenv("MAX_RETRIES", "5")
    monkeypatch.setenv("CONNECTOR_API_KEY", "secret-agent-key")

    s = Settings()
    assert str(s.base_url) == "https://store.example.com/"
    assert s.consumer_key == "ck_prod_key"
    assert s.consumer_secret == "cs_prod_secret"
    assert s.pii_mode == PIIMode.FULL
    assert s.max_page_size == 75
    assert s.rate_limit_rps == 10.0
    assert s.request_timeout == 30.0
    assert s.max_retries == 5
    assert s.connector_api_key == "secret-agent-key"


def test_fail_fast_on_missing_required():
    s = Settings(base_url="http://localhost:8080", consumer_key="", consumer_secret="")
    with pytest.raises(ConfigurationError) as exc_info:
        s.validate_required()

    assert "Missing required WooCommerce configuration" in str(exc_info.value)
    assert "WOO_CONSUMER_KEY" in str(exc_info.value)
    assert "WOO_CONSUMER_SECRET" in str(exc_info.value)


def test_get_settings_strict():
    with pytest.raises(ConfigurationError):
        get_settings(strict=True, consumer_key="", consumer_secret="")


def test_invalid_base_url_scheme():
    with pytest.raises((ConfigurationError, ValidationError)) as exc_info:
        Settings(base_url="ftp://invalid-url.com")
    assert "must start with http:// or https://" in str(exc_info.value)


def test_mask_secret_helper():
    assert mask_secret(None) == "<not-set>"
    assert mask_secret("") == "<not-set>"
    assert mask_secret("abc") == "***"
    assert mask_secret("cs_1234567890") == "cs_1...[REDACTED]"


def test_secret_masking_in_repr_and_str():
    secret_key = "ck_sensitive_key_99999"
    secret_val = "cs_sensitive_secret_88888"
    token = "bearer_very_secret_token"

    s = Settings(
        base_url="https://secure-store.com",
        consumer_key=secret_key,
        consumer_secret=secret_val,
        connector_api_key=token,
    )

    repr_str = repr(s)
    str_val = str(s)

    assert secret_key not in repr_str
    assert secret_val not in repr_str
    assert token not in repr_str

    assert secret_key not in str_val
    assert secret_val not in str_val
    assert token not in str_val

    assert "cs_s...[REDACTED]" in repr_str
    assert "ck_s...[REDACTED]" in repr_str
