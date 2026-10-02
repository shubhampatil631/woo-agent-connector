# WooCommerce Connector for Razorpay Agent Studio

A high-performance, private, read-only connector enabling Agent Studio agents to query WooCommerce orders and inventory safely with built-in PII redaction and rate-limit handling.

## Architecture & Principles
- **Read-Only**: Strictly no write or delete operations.
- **PII-Safe**: Automatically masks sensitive customer PII unless explicitly configured.
- **Agent-Friendly**: Compact JSON outputs, bounded pagination, actionable error states.
- **Standardized**: Built with FastMCP over Model Context Protocol.

## Project Structure
```text
woo-agent-connector/
├── src/woo_connector/
│   ├── __init__.py
│   ├── config.py
│   ├── auth.py
│   ├── client.py
│   ├── models.py
│   ├── tools.py
│   └── server.py
├── tests/
├── scripts/
├── docs/
├── docker/
├── pyproject.toml
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

## Local WooCommerce Sandbox Setup

The repository provides a complete local WordPress + WooCommerce environment configured with pretty permalinks and automatic read-only REST API key generation.

### 1. Start Sandbox
```bash
# Start Docker containers and monitor initialization
make up
# or: docker compose up -d && docker compose logs -f wpcli
```

The `wpcli` container will automatically:
1. Wait for MariaDB to become healthy.
2. Install WordPress.
3. Install and activate the WooCommerce plugin.
4. Enable pretty permalinks (`/%postname%/`) required by `/wp-json/wc/v3/`.
5. Generate a read-only REST API Key pair and print it to stdout.

### 2. Configure Environment
Copy the generated credentials printed in the container console into your local `.env`:
```bash
cp .env.example .env
```
Edit `.env`:
```env
WOO_STORE_URL=http://localhost:8080
WOO_CONSUMER_KEY=ck_your_generated_key
WOO_CONSUMER_SECRET=cs_your_generated_secret
WOO_AUTH_TYPE=api_key
WOO_PII_MODE=redacted
```

### 3. Seed Sandbox Catalog & Orders
Populate the store with ~40 fictional products and ~120 realistic orders across 7 distinct WooCommerce statuses:
```bash
make seed
# or: python scripts/seed.py
```

## Available Makefile Commands

| Command | Action |
|---|---|
| `make up` | Starts sandbox & generates read-only API credentials |
| `make down` | Stops sandbox containers |
| `make seed` | Seeds ~40 products & ~120 orders with fake customer data |
| `make test` | Runs the test suite |
| `make lint` | Runs Ruff linter checks |
| `make format` | Formats code with Ruff |
| `make run` | Starts the FastMCP connector server |
| `make install`| Installs dependencies in editable mode |
| `make clean` | Cleans build and cache files |

