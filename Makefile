.PHONY: install test lint format serve

install:
	uv sync --dev

test:
	uv run pytest

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

serve:
	uv run paotui serve
