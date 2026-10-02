# WooCommerce Connector for Razorpay Agent Studio

A high-performance, private, read-only connector enabling Agent Studio agents to query WooCommerce orders and inventory safely with built-in PII redaction and rate-limit handling.

## Architecture & Principles
- **Read-Only**: Strictly no write or delete operations.
- **PII-Safe**: Automatically masks sensitive customer PII unless explicitly configured.
- **Agent-Friendly**: Compact JSON outputs, bounded pagination, actionable error states.
- **Standardized**: Built with FastMCP over Model Context Protocol.

## Project Structure
```text
woo-connector/
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

## Quick Start
```bash
# Create virtual environment and install dependencies
uv venv
uv pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .
```
