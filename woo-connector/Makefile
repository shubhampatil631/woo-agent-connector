.PHONY: help install test lint format clean docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  install      Install dependencies with uv / pip"
	@echo "  test         Run tests with pytest"
	@echo "  lint         Run ruff checks"
	@echo "  format       Format code with ruff"
	@echo "  clean        Remove temporary files and caches"
	@echo "  docker-up    Start local WooCommerce sandbox"
	@echo "  docker-down  Stop local WooCommerce sandbox"

install:
	uv pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check .

format:
	ruff format .

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ src/**/__pycache__ tests/__pycache__ dist build *.egg-info

docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down
