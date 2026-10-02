# Razorpay Agent Studio: WooCommerce Connector Submission

**Repository**: [https://github.com/shubhampatil631/woo-agent-connector](https://github.com/shubhampatil631/woo-agent-connector)  
**Role**: Forward-Deployed Engineer (FDE), Agent Studio  
**Author**: Shubham Patil  
**Version**: `v1.0.0`

---

## 1. 10-Line Setup (Zero to Working Demo)

```bash
git clone https://github.com/shubhampatil631/woo-agent-connector.git
cd woo-agent-connector
python -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env            # Defaults work out-of-the-box with mock server
python scripts/demo.py --mock   # Step-by-step interactive CLI demo (100% offline)
pytest -v --cov=src/woo_connector # Runs 72 tests (90% coverage)
python scripts/agent_demo.py --mock # Full LLM tool-calling agent simulation
woo-mcp                         # Launches production FastMCP server (stdio)
```

---

## 2. Core Architecture & Design Decisions

- **Strict Read-Only Guarantee**: Zero mutation or write tools registered. Even raw client requests explicitly reject any HTTP method other than `GET` at runtime.
- **Client-Side Token Bucket Limiter**: Smooths bursts into a consistent rate (`WOO_RATE_LIMIT_RPS=5`), preventing upstream rate limit triggers.
- **Jittered Exponential Backoff**: Automatically absorbs transient `429 Too Many Requests` (respecting `Retry-After` header) and upstream gateway faults (`502`, `503`, `504`).
- **Connector-Level PII Redaction**: Default `PII_MODE=redacted` masks customer emails (`j***@example.com`), phone numbers (`***-***-**67`), and addresses before data ever enters the LLM context window.
- **Dual MCP Transports**: Supports zero-overhead `stdio` for local LLM runtimes (Claude Desktop, Cursor) and streamable HTTP with Bearer token authentication for cloud Agent Studio runtimes.

---

## 3. Assumptions

1. **Upstream API**: WooCommerce v3 REST API (`/wp-json/wc/v3/`) available over HTTPS (or HTTP in local dev).
2. **Authentication**: WooCommerce REST API Keys (Consumer Key + Consumer Secret) or OAuth 1.0a access tokens with `read` permissions.
3. **Agent Role**: The agent acts as an automated customer support / operations assistant for WISMO ("Where is my order?"), stock checks, and catalog discovery. State mutations (refunds, cancellations, inventory edits) remain behind human approval.
4. **Data Freshness**: Stock inquiries represent real-time database state at query time. High-velocity flash sales may experience slight eventual consistency across concurrent checkouts.

---

## 4. Known Limitations & Roadmap

| Current Limitation | Production Solution / Roadmap |
| :--- | :--- |
| **Pull-Based Polling** | Implement WooCommerce webhook listeners into Redis cache for instant cache invalidation. |
| **Single Store per Process** | Add multi-tenant credential isolation keyed on `X-Merchant-ID` header. |
| **API Key Storage** | Integrate with Razorpay Merchant KMS / Vault for hardware-secured token management. |
| **Page-Bounded Queries** | Cursor-based streaming for multi-page bulk data analytics. |

