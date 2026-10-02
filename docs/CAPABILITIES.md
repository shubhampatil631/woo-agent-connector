# WooCommerce Agent Studio Connector: Capabilities & Boundaries

This document defines the strict operational boundaries, capabilities, and safety guardrails of the WooCommerce MCP Connector for Razorpay Agent Studio.

---

## 1. What the Agent CAN Do (Supported Capabilities)

The connector provides **9 read-only primitives** allowing agents to query store data without mutating state:

### Order Primitives
- **`list_orders`**: Filter orders by status (`pending`, `processing`, `on-hold`, `completed`, `cancelled`, `refunded`, `failed`), customer ID, or ISO-8601 date ranges (`after`, `before`). Returns compact `OrderSummary` items.
- **`get_order`**: Inspect complete line items, variation IDs, pricing, discount totals, shipping costs, refund records, and delivery details for a known order ID.
- **`search_orders`**: Search orders across order numbers, customer names, emails, and address fields via partial keyword matching.

### Product & Inventory Primitives
- **`list_products`**: Browse the store catalog with status and stock availability (`instock`, `outofstock`, `onbackorder`) filters.
- **`get_product`**: Retrieve full product metadata, pricing, SKU, and stock management configuration.
- **`search_products`**: Search catalog items by text query matching name/description or by exact SKU.
- **`get_stock`**: Real-time stock level and low-stock alert query for any product ID or SKU.
- **`list_low_stock`**: Scan the catalog for products at or below a stock threshold (default: 5 units) or marked as out-of-stock.

### Store Status & Self-Discovery Resources
- **`get_store_status`** & **`woo://store/status`**: Verify store connectivity, WooCommerce/WordPress versions, base currency, and timezone.
- **`woo://docs/capabilities`**: Serves this document to allow agent runtime self-discovery.

### Privacy & Redaction
- **Automatic PII Redaction (`PII_MODE=redacted`)**: Automatically masks emails (`j***@example.com`), phone numbers (`***-***-**67`), and addresses (city/state/country only) before reaching the agent's context window.

---

## 2. What the Agent CANNOT Do (Enforced Guardrails)

To guarantee store security and eliminate blast radius, the connector explicitly forbids:

1. **Zero Write or State Mutations**:
   - CANNOT create, modify, cancel, refund, or fulfill orders.
   - CANNOT update product prices, descriptions, or inventory levels.
   - CANNOT create or delete customers or coupons.
2. **No Access to Payment Card Data**:
   - CANNOT access credit card numbers, CVVs, expiry dates, or banking tokens (PCI-DSS boundary).
3. **No Unmasked PII in Default Mode**:
   - CANNOT view raw customer emails or phone numbers unless `PII_MODE=full` is explicitly enabled.
4. **No Arbitrary SQL or Unindexed Querying**:
   - CANNOT search by custom metadata fields not supported by WooCommerce core REST filters.
5. **No Instantaneous Real-Time Stock Guarantees**:
   - Stock counts reflect upstream WooCommerce database state at query time; eventual consistency applies if high-concurrency checkouts occur concurrently.
6. **No Bulk Data Exfiltration**:
   - CANNOT export unbounded datasets in a single call. Page sizes are capped at 100 items (`MAX_PAGE_SIZE=50` default).
7. **No Event Subscriptions or Webhooks**:
   - The connector operates on a request-response pull model; it does not receive incoming webhooks.
8. **No Multi-Store Switching per Session**:
   - A connector instance binds to one store per configuration.

---

## 3. Safe Usage & Agent Decision Guide

### Example Queries: Good vs. Bad Agent Patterns

| User Request | Recommended Tool & Parameters | What NOT to Do |
| :--- | :--- | :--- |
| *"Which orders failed this week?"* | `list_orders(status='failed', after='2026-09-25T00:00:00')` | Do NOT pull all orders and filter in LLM context. |
| *"What is our stock on SKU SLEEVE-LTH-01?"* | `get_stock(product_id_or_sku='SLEEVE-LTH-01')` | Do NOT run `list_products` across the entire store. |
| *"Find orders for customer Jane Doe"* | `search_orders(query='Jane Doe')` | Do NOT call `list_orders` without filters. |
| *"Cancel order #1042"* | **Refuse request:** Explain connector is read-only and guide human operator. | Do NOT hallucinate a cancellation tool. |

### Error Handling & Retry Protocol

When tools encounter upstream errors, they return structured payloads with an actionable `agent_message`:

```json
{
  "code": "RATE_LIMITED",
  "message": "WooCommerce API rate limit reached. Please retry in 5 seconds.",
  "retryable": true,
  "retry_after": 5.0
}
```

- **`RATE_LIMITED` (429) & `UPSTREAM_ERROR` (502/503/504)**: The connector client automatically retries up to 3 times with exponential backoff + jitter. If exhausted, the agent must inform the merchant and wait `retry_after` seconds.
- **`NOT_FOUND` (404)**: Agent should inform the user that the ID/SKU does not exist and ask for clarification.
- **`AUTH_FAILED` (401/403)**: Agent must instruct the administrator to check API key permissions.

### Why `per_page` is Bounded
Bounding page sizes (`MAX_PAGE_SIZE <= 100`) prevents upstream PHP memory exhaustion in shared hosting environments and prevents LLM context window blowups. Agents traverse large collections by following the `has_more: true` pagination flag across consecutive pages.
