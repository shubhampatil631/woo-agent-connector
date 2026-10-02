.PHONY: help install up down seed test lint format run demo demo-mock agent-demo clean

help:
	@echo "Available commands:"
	@echo "  up           Start local WooCommerce sandbox and initialize store with API keys"
	@echo "  down         Stop local WooCommerce sandbox"
	@echo "  seed         Seed sandbox with ~40 products and ~120 orders across statuses"
	@echo "  test         Run test suite with pytest and coverage"
	@echo "  lint         Run ruff linter checks"
	@echo "  format       Format code with ruff"
	@echo "  run          Start the FastMCP WooCommerce server"
	@echo "  demo         Run end-to-end interactive demo against configured store"
	@echo "  demo-mock    Run end-to-end interactive demo against mock store (zero dependencies)"
	@echo "  agent-demo   Run LLM tool-calling agent demo on merchant questions"
	@echo "  install      Install connector dependencies in editable mode"
	@echo "  clean        Remove build, test, and cache artifacts"

install:
	pip install -e ".[dev]"

up:
	docker compose up -d
	@echo "Waiting for WooCommerce sandbox to complete initialization..."
	docker compose logs -f wpcli

down:
	docker compose down

seed:
	python scripts/seed.py

test:
	pytest -v --cov=src/woo_connector --cov-report=term-missing

lint:
	ruff check .

format:
	ruff format .

run:
	woo-mcp

demo:
	python scripts/demo.py

demo-mock:
	python scripts/demo.py --mock

agent-demo:
	python scripts/agent_demo.py

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ src/**/__pycache__ tests/__pycache__ dist build *.egg-info .coverage
