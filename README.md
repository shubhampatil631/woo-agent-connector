# WooCommerce Connector for Razorpay Agent Studio

A production-grade, private, read-only Model Context Protocol (MCP) connector enabling Razorpay Agent Studio agents to securely query WooCommerce orders, products, and inventory with automated PII redaction and rate-limit resilience.

---

## Architecture & Core Guardrails

- **Strictly Read-Only**: Zero write, mutation, or delete tools exist. Upstream requests strictly prohibit non-GET HTTP methods.
- **PII-Safe by Default**: Automatically redacts customer emails (`j***@example.com`), phone numbers (`***-***-**67`), and addresses unless `PII_MODE=full` is explicitly set.
- **Client-Side Token-Bucket Rate Limiter**: Shared, concurrency-safe token bucket honoring `RATE_LIMIT_RPS` with exponential backoff + full jitter on HTTP 429, 502, 503, 504, and network timeouts.
- **MCP Self-Discovery Resources**: Dynamic `woo://store/status` and `woo://docs/capabilities` MCP resources allow agents to inspect store connectivity and query limits autonomously.
- **Startup Credential Validation**: Proactively validates API credentials on boot and refuses startup if `STRICT_READONLY=true` and write-capable keys are provided.
- **Standardized Machine-Readable Spec**: Introspects registered tools dynamically via `scripts/export_spec.py` into `docs/mcp-tools.json`.

---

## Project Structure

```text
woo-agent-connector/
├── src/woo_connector/
│   ├── __init__.py
│   ├── config.py         # Pydantic v2 settings with secret masking __repr__
│   ├── auth.py           # API-Key (HTTPS Basic / HTTP query) & OAuth strategies
│   ├── client.py         # Async WooClient with TokenBucket rate limiter & retries
│   ├── models.py         # Compact, agent-friendly domain schemas
│   ├── redact.py         # PII masking engine (email, phone, address, customer ref)
│   ├── tools.py          # 9 transport-agnostic read primitives
│   └── server.py         # FastMCP server (stdio & streamable HTTP transports)
├── tests/
│   ├── mock_woo.py       # Configurable mock WooCommerce server (429/503 simulation)
│   ├── test_e2e_mcp.py   # In-process MCP tool execution tests
│   ├── test_client.py    # Rate limiter, backoff, and non-GET rejection tests
│   ├── test_tools.py     # Tool validation and exception mapping tests
│   ├── test_auth.py      # Basic Auth, query auth, and credential checks
│   ├── test_config.py    # Settings validation and masking tests
│   ├── test_redact.py    # PII masking unit tests
│   └── test_server.py    # MCP server registration and Bearer auth tests
├── scripts/
│   ├── demo.py           # Rich end-to-end interactive demo (--mock or live)
│   ├── agent_demo.py     # LLM tool-calling agent loop (Anthropic API / simulated)
│   ├── export_spec.py    # MCP tool specification exporter (docs/mcp-tools.json)
│   ├── authorize_app.py  # Local helper for WooCommerce OAuth app approval flow
│   └── seed.py           # Seeds local sandbox with ~40 products & ~120 orders
├── docs/
│   ├── CAPABILITIES.md   # Connector capabilities, guardrails, and error mappings
│   └── mcp-tools.json    # Machine-readable MCP JSON tool specification
├── examples/
│   └── agent_studio_config.json # Agent Studio stdio and HTTP registration template
├── docker/
│   ├── docker-compose.yml       # Local WordPress + WooCommerce + MariaDB sandbox
│   └── init-woocommerce.sh      # Sandbox bootstrapping script
├── pyproject.toml
├── Makefile
├── .env.example
└── README.md
```

---

## Quickstart (Zero-Dependency Mock Demonstration)

To immediately run and inspect the connector without setting up external services or Docker:

```bash
# 1. Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 2. Install dependencies in editable mode
pip install -e ".[dev]"

# 3. Run rich interactive verification demo against in-process mock
python scripts/demo.py --mock
# or: make demo-mock
```

---

## Local WooCommerce Sandbox Setup (Docker)

The repository provides a complete local WordPress + WooCommerce environment configured with pretty permalinks and automatic read-only REST API key generation.

### 1. Start Docker Sandbox
```bash
make up
# or: docker compose up -d && docker compose logs -f wpcli
```

The initialization container will automatically:
1. Wait for MariaDB to become healthy.
2. Install WordPress and configure site settings.
3. Install and activate the WooCommerce plugin.
4. Enable pretty permalinks (`/%postname%/`) required by `/wp-json/wc/v3/`.
5. Generate a read-only REST API Key pair and print it to console.

### 2. Configure Local `.env`
Copy `.env.example` and populate with the generated credentials:
```bash
cp .env.example .env
```

```env
WOO_BASE_URL=http://localhost:8080
WOO_CONSUMER_KEY=ck_your_generated_key
WOO_CONSUMER_SECRET=cs_your_generated_secret
WOO_AUTH_TYPE=api_key
WOO_PII_MODE=redacted
STRICT_READONLY=false
WOO_RATE_LIMIT_RPS=5
CONNECTOR_API_KEY=secret_mcp_bearer_token
```

### 3. Seed Realistic Products & Orders
Populate the store with parent products, variations, stock scenarios, and orders distributed across 7 distinct WooCommerce lifecycle states:
```bash
make seed
# or: python scripts/seed.py
```

### 4. Run Live Store Demo
```bash
make demo
# or: python scripts/demo.py
```

---

## Running the FastMCP Server

### 1. stdio Transport (Default for Agent Studio & Desktop Agents)
```bash
woo-mcp
# or: python -m woo_connector.server --transport stdio
```

### 2. HTTP/SSE Streamable Transport
Secured via `CONNECTOR_API_KEY` Bearer authentication:
```bash
python -m woo_connector.server --transport http --port 8000
```
*Requests must include `Authorization: Bearer <CONNECTOR_API_KEY>` or they are rejected with HTTP 401.*

### 3. MCP Inspector (Interactive Browser UI)
Inspect and execute all 9 tools visually using the official Model Context Protocol Inspector:
```bash
npx @modelcontextprotocol/inspector python -m woo_connector.server
```

---

## Available Makefile Commands

| Command | Action |
|---|---|
| `make test` | Runs full test suite with coverage report (target >= 85%) |
| `make demo-mock` | Runs zero-dependency rich interactive demonstration |
| `make demo` | Runs interactive demo against live configured store |
| `make agent-demo` | Runs LLM tool-calling agent loop on merchant questions |
| `make up` | Starts Docker sandbox & generates read-only API credentials |
| `make seed` | Seeds catalog products and orders into store |
| `make down` | Stops Docker sandbox containers |
| `make lint` | Runs Ruff linter checks |
| `make format` | Formats code with Ruff |
| `make run` | Starts the FastMCP server in stdio mode |
| `make install` | Installs connector dependencies in editable mode |
| `make clean` | Cleans cache, build, and coverage artifacts |
