.PHONY: help install up down seed test lint format run clean

help:
	@echo "Available commands:"
	@echo "  up           Start local WooCommerce sandbox and initialize store with API keys"
	@echo "  down         Stop local WooCommerce sandbox"
	@echo "  seed         Seed sandbox with ~40 products and ~120 orders across statuses"
	@echo "  test         Run test suite with pytest"
	@echo "  lint         Run ruff linter checks"
	@echo "  format       Format code with ruff"
	@echo "  run          Start the FastMCP WooCommerce server"
	@echo "  install      Install connector dependencies in editable mode"
	@echo "  clean        Remove build, test, and cache artifacts"

install:
	uv pip install -e ".[dev]"

up:
	docker compose up -d
	@echo "Waiting for WooCommerce sandbox to complete initialization..."
	docker compose logs -f wpcli

down:
	docker compose down

seed:
	python scripts/seed.py

test:
	pytest -v

lint:
	ruff check .

format:
	ruff format .

run:
	woo-mcp

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ src/**/__pycache__ tests/__pycache__ dist build *.egg-info
