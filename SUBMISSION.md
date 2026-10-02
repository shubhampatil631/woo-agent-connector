# Razorpay Forward-Deployed Engineer Assignment Submission

**Candidate**: Shubham Patil (`sup31patil@gmail.com`)  
**Role**: Forward-Deployed Engineer, Agent Studio  
**Repository**: [https://github.com/shubhampatil631/woo-agent-connector](https://github.com/shubhampatil631/woo-agent-connector)  
**Release Tag**: `v1.0.0`

---

## 10-Line Quickstart Setup

```bash
git clone https://github.com/shubhampatil631/woo-agent-connector.git && cd woo-agent-connector
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -v --cov=src/woo_connector                # 69/69 tests pass (90% coverage)
python scripts/demo.py --mock                     # 7-step interactive verification demo
# --- Optional: Local WooCommerce Docker Store ---
docker compose up -d                             # Bootstraps WP, Woo & read-only keys
cp .env.example .env                             # Populate keys from docker logs
python scripts/seed.py                           # Seeds 40+ products & 120+ orders
python -m woo_connector.server --transport stdio # Starts FastMCP server
npx @modelcontextprotocol/inspector python -m woo_connector.server # Opens Web UI
```

---

## Technical Assumptions

1. **API Protocol**: Targets standard WooCommerce REST API v3 (`/wp-json/wc/v3/`) available in WooCommerce 3.5+.
2. **Read-Only Scope**: The connector operates as a read-only observability and inquiry layer for Agent Studio. Write actions are strictly rejected at the client and tool layers to eliminate risk of unauthorized store mutations.
3. **Privacy Compliance**: Customer PII (emails, phone numbers, addresses) is masked by default (`PII_MODE=redacted`) before reaching LLM agent context.
4. **Transport Flexibility**: Supports `stdio` for local Agent Studio instances and streamable `http/sse` protected by constant-time Bearer token authentication (`CONNECTOR_API_KEY`) for remote deployments.

---

## Known Limitations & Production Recommendations

1. **No Mutation Primitives (By Design)**: Does not support order state updates, refunds, or inventory adjustments. Write primitives should be implemented behind dedicated two-phase approval workflows.
2. **Polling vs Webhooks**: Connector uses on-demand pull queries. For event-driven workflows (e.g. immediate payment alerts), integrate WooCommerce webhooks directly into Razorpay webhook ingestion.
3. **Bulk Export Bounds**: Individual queries are capped at 50 items (max 100) per page. Historical analytics over 100,000+ orders should query analytical data warehouses (e.g. Snowflake/BigQuery) rather than live store REST APIs.

---

## 90-Second Walkthrough Script (Screen Recording)

- **[0:00 - 0:15] Introduction & Architecture Overview**
  - *"Hi! This is the WooCommerce MCP Connector built for Razorpay Agent Studio. It provides 9 read-only primitives for orders, products, and inventory with zero write tools and automatic PII masking."*
  - Show repository layout and `src/woo_connector/` structure.

- **[0:15 - 0:40] Zero-Dependency Interactive Demo (`python scripts/demo.py --mock`)**
  - Run `python scripts/demo.py --mock` in the terminal.
  - Point out Step 1 (credential verification), Step 2 (bounded order pagination), Step 4 (PII redaction masking emails to `c***@example.com` and phones to `***-***-**01`), Step 6 (automatic exponential backoff and recovery on HTTP 429), and Step 7 (actionable LLM error relay on invalid credentials).

- **[0:40 - 1:05] FastMCP Server & MCP Inspector (`npx @modelcontextprotocol/inspector`)**
  - Launch `npx @modelcontextprotocol/inspector python -m woo_connector.server`.
  - Open browser UI: show registered tools (`list_orders`, `get_stock`, `list_low_stock`) and MCP resource `woo://docs/capabilities`.
  - Execute `list_orders` and `get_stock` live in the inspector.

- **[1:05 - 1:20] Automated Test Suite & Coverage (`make test`)**
  - Run `pytest -v --cov=src/woo_connector`.
  - Highlight: 69 passing tests, 90% code coverage across `src/woo_connector/`, zero secrets in repository history.

- **[1:20 - 1:30] Configuration & Agent Studio Registration**
  - Show `examples/agent_studio_config.json` demonstrating how to connect the tool to Agent Studio over stdio and HTTP.
  - Conclude: *"Production-ready, tested, and fully aligned with Agent Studio requirements."*
