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

---

## 5. 90-Second Screen Recording Walkthrough Script

*Target duration: 90 seconds. Ideal for Loom / video walkthrough.*

```
[0:00 - 0:15] Introduction & Architecture
"Hi everyone, I'm Shubham. Today I'm demonstrating the WooCommerce MCP Connector 
built for Razorpay Agent Studio. It is a strictly read-only, resilient bridge that 
allows AI agents to query orders, catalog, and inventory safely with built-in PII 
redaction and rate-limit backoff."

[0:15 - 0:35] Zero-Dependency Verification Demo (`python scripts/demo.py --mock`)
"Let's run our zero-dependency verification demo.
Notice what happens here:
1. It validates store credentials and discovers WooCommerce capabilities.
2. It fetches recent orders with customer emails and addresses automatically masked.
3. It runs an inventory lookup and low-stock report across SKUs.
4. It simulates an upstream 429 rate limit with a 2-second Retry-After header, 
   smoothly backing off and recovering without crashing the agent."

[0:35 - 0:55] Autonomous LLM Agent Loop (`python scripts/agent_demo.py --mock`)
"Now let's run our end-to-end agent simulation.
An LLM receives real user questions like 'Where is my order 1001?' and 'Do we have 
leather sleeves in stock?'.
The agent autonomously selects `get_order` and `get_stock`, inspects the redacted 
payloads, and generates clear, professional answers for the merchant."

[0:55 - 1:15] Test Suite & Code Quality (`pytest -v --cov`)
"Let's inspect our test suite:
72 tests covering authentication strategies, token bucket math, retry backoff, 
PII masking, and FastMCP tool execution across both stdio and HTTP transports.
We have 90% test coverage with zero lint errors on Ruff and clean typing on MyPy."

[1:15 - 1:30] Wrap-up & Agent Studio Integration
"The connector exports an auto-generated machine-readable MCP tool specification in 
docs/mcp-tools.json and connects seamlessly to Agent Studio via stdio or authenticated 
HTTP. Thanks for watching!"
```
