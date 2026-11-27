.PHONY: install test lint format eval eval-quick docs

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
	uv run python eval/run.py

eval-quick:
	uv run python eval/run.py --quick

docs:
	uv run --group docs mkdocs build --strict
