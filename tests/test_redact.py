"""Unit tests for PII redaction engine."""

from woo_connector.config import PIIMode
from woo_connector.redact import (
    redact_address,
    redact_customer_ref,
    redact_email,
    redact_name,
    redact_phone,
)


def test_redact_email_default():
    assert redact_email("john.doe@example.com") == "j***@example.com"
    assert redact_email("a@b.com") == "a***@b.com"
    assert redact_email("") == ""
    assert redact_email(None) == ""
    assert redact_email("notanemail") == "***"


def test_redact_email_full():
    assert redact_email("john.doe@example.com", mode=PIIMode.FULL) == "john.doe@example.com"


def test_redact_phone_default():
    assert redact_phone("+1-555-123-4567") == "***-***-**67"
    assert redact_phone("9876543210") == "***-***-**10"
    assert redact_phone("12") == "***"
    assert redact_phone("") == ""
    assert redact_phone(None) == ""


def test_redact_phone_full():
    assert redact_phone("+1-555-123-4567", mode=PIIMode.FULL) == "+1-555-123-4567"


def test_redact_name():
    assert redact_name("John", "Doe") == "John D."
    assert redact_name("Alice", "") == "Alice"
    assert redact_name("", "Smith") == "S."
    assert redact_name("", "") == "[Customer]"
    assert redact_name("John", "Doe", mode=PIIMode.FULL) == "John Doe"


def test_redact_customer_ref():
    assert redact_customer_ref(42, "user@example.com") == "Customer #42"
    assert redact_customer_ref(0, "user@example.com") == "u***@example.com"
    assert redact_customer_ref(None, None) == "Guest Customer"


def test_redact_address_redacted():
    raw_addr = {
        "first_name": "John",
        "last_name": "Doe",
        "company": "Acme Corp",
        "address_1": "123 Main St",
        "address_2": "Suite 500",
        "city": "Seattle",
        "state": "WA",
        "postcode": "98101",
        "country": "US",
        "email": "john.doe@example.com",
        "phone": "+1-555-123-4567",
    }
    redacted = redact_address(raw_addr, mode=PIIMode.REDACTED)

    assert redacted["full_name"] == "John D."
    assert redacted["company"] == "[REDACTED]"
    assert redacted["address_1"] == "[REDACTED]"
    assert redacted["address_2"] == "[REDACTED]"
    assert redacted["city"] == "Seattle"
    assert redacted["state"] == "WA"
    assert redacted["postcode"] == "98101"
    assert redacted["country"] == "US"
    assert redacted["email"] == "j***@example.com"
    assert redacted["phone"] == "***-***-**67"


def test_redact_address_full():
    raw_addr = {
        "first_name": "John",
        "last_name": "Doe",
        "company": "Acme Corp",
        "address_1": "123 Main St",
        "city": "Seattle",
        "state": "WA",
        "postcode": "98101",
        "country": "US",
    }
    full = redact_address(raw_addr, mode=PIIMode.FULL)

    assert full["full_name"] == "John Doe"
    assert full["company"] == "Acme Corp"
    assert full["address_1"] == "123 Main St"
    assert full["city"] == "Seattle"
