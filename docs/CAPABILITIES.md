# WooCommerce Agent Studio Connector Capabilities

## Overview
This connector is a private, read-only integration layer allowing Razorpay Agent Studio agents to securely query WooCommerce store data, orders, catalog items, and inventory levels.

---

## What the Agent CAN Do (Supported Capabilities)

1. **Order Management & Inspection**:
   - List recent orders with pagination and filtering by status (`pending`, `processing`, `on-hold`, `completed`, `cancelled`, `refunded`, `failed`).
   - Filter orders created after or before specific ISO 8601 timestamps.
   - Filter orders by customer ID.
   - Retrieve complete order details (line items, item count, currency, payment method, refund records).
   - Search orders by order number, customer name, email address, or billing details.

2. **Catalog & Inventory Queries**:
   - Browse store products with category and stock status (`instock`, `outofstock`, `onbackorder`) filters.
   - Search products by text keyword or exact SKU.
   - Fetch real-time stock levels, stock quantity, and backorder status for any product ID or SKU.
   - Identify low-stock items at or below a configurable threshold (default: 5 units).

3. **Store Health & Metadata**:
   - Verify store connectivity, WooCommerce/WordPress versions, base currency, and timezone.

4. **Privacy & PII Protection**:
   - By default (`PII_MODE=redacted`), all customer email addresses, phone numbers, and physical street addresses are automatically masked before being relayed to the LLM.

---

## What the Agent CANNOT Do (Enforced Limitations & Guardrails)

1. **No Write or Mutation Capabilities**:
   - The connector has **zero write, update, or delete tools**.
   - The agent cannot create, update, cancel, refund, or delete orders.
   - The agent cannot update prices, modify stock quantities, or edit product descriptions.

2. **No Access to Customer Payment Instruments**:
   - Credit card numbers, CVVs, bank tokens, and payment credentials are never accessible or stored.

3. **Bounded Query Limits**:
   - All list queries are strictly bounded (maximum 50 items per page by default, clamped at 100) to prevent context window saturation.
   - Rate limiting is enforced (default: 5 requests/sec) to avoid stressing upstream store servers.

---

## Error Handling & Recovery

All tools map errors to structured, actionable agent messages:
- `AUTH_FAILED`: Credentials lack permissions or are invalid.
- `NOT_FOUND`: The queried order or product ID does not exist.
- `RATE_LIMITED`: API quota reached; includes `retry_after` delay.
- `UPSTREAM_ERROR`: Store server is temporarily offline; retryable with backoff.
- `INVALID_INPUT`: Malformed parameters (e.g., invalid date format or negative page numbers).
