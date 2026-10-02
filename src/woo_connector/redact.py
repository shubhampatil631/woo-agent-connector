"""PII redaction engine for customer privacy in Agent Studio workflows."""

import re
from typing import Any

from woo_connector.config import PIIMode


def redact_email(email: str | None, mode: PIIMode = PIIMode.REDACTED) -> str:
    """Mask email address (e.g., 'john.doe@example.com' -> 'j***@example.com')."""
    if mode == PIIMode.FULL or not email:
        return email or ""

    email_clean = email.strip()
    if "@" not in email_clean:
        return "***"

    user_part, domain_part = email_clean.split("@", 1)
    if not user_part:
        return f"***@{domain_part}"

    first_char = user_part[0]
    return f"{first_char}***@{domain_part}"


def redact_phone(phone: str | None, mode: PIIMode = PIIMode.REDACTED) -> str:
    """Mask phone number preserving only the last 2 digits."""
    if mode == PIIMode.FULL or not phone:
        return phone or ""

    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 2:
        return "***"

    last_two = digits[-2:]
    return f"***-***-**{last_two}"


def redact_name(
    first_name: str | None,
    last_name: str | None = None,
    mode: PIIMode = PIIMode.REDACTED,
) -> str:
    """Format name as First Name + Last Initial (e.g., 'John Doe' -> 'John D.')."""
    first = (first_name or "").strip()
    last = (last_name or "").strip()

    if mode == PIIMode.FULL:
        return f"{first} {last}".strip()

    if not first and not last:
        return "[Customer]"

    if first and last:
        return f"{first} {last[0]}."
    if first:
        return first
    return f"{last[0]}."


def redact_customer_ref(
    customer_id: int | None,
    email: str | None = None,
    mode: PIIMode = PIIMode.REDACTED,
) -> str:
    """Build a safe customer reference string."""
    if customer_id and customer_id > 0:
        return f"Customer #{customer_id}"
    if email:
        return redact_email(email, mode=mode)
    return "Guest Customer"


def redact_address(
    address: dict[str, Any] | None,
    mode: PIIMode = PIIMode.REDACTED,
) -> dict[str, Any]:
    """Redact detailed street addresses while preserving geographic city/state/country."""
    if not address:
        return {}

    if mode == PIIMode.FULL:
        first = address.get("first_name", "")
        last = address.get("last_name", "")
        full_name = f"{first} {last}".strip()
        return {
            "first_name": first,
            "last_name": last,
            "full_name": full_name or None,
            "company": address.get("company") or None,
            "address_1": address.get("address_1") or None,
            "address_2": address.get("address_2") or None,
            "city": address.get("city") or None,
            "state": address.get("state") or None,
            "postcode": address.get("postcode") or None,
            "country": address.get("country") or None,
            "email": address.get("email") or None,
            "phone": address.get("phone") or None,
        }

    first = address.get("first_name", "")
    last = address.get("last_name", "")

    return {
        "first_name": first if first else None,
        "last_name": f"{last[0]}." if last else None,
        "full_name": redact_name(first, last, mode=mode),
        "company": "[REDACTED]" if address.get("company") else None,
        "address_1": "[REDACTED]" if address.get("address_1") else None,
        "address_2": "[REDACTED]" if address.get("address_2") else None,
        "city": address.get("city") or None,
        "state": address.get("state") or None,
        "postcode": address.get("postcode") or None,
        "country": address.get("country") or None,
        "email": redact_email(address.get("email"), mode=mode) if address.get("email") else None,
        "phone": redact_phone(address.get("phone"), mode=mode) if address.get("phone") else None,
    }
