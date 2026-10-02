"""Basic skeleton test."""

from woo_connector.config import AuthType, PIIMode, Settings


def test_default_config():
    s = Settings(
        consumer_key="ck_dummy",
        consumer_secret="cs_dummy",
    )
    assert s.auth_type == AuthType.API_KEY
    assert s.pii_mode == PIIMode.REDACTED
    assert s.max_page_size == 50
