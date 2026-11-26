.PHONY: install test lint format eval

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

eval:
	@echo "No evaluation yet: the harness arrives in milestone M7 (docs/steps-v0.1.md)."
