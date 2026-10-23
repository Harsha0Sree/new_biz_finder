.PHONY: install test lint format validate check aggregate reports pipeline

install:
	uv sync

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

validate:
	uv run python -m scanner.validate

check: lint test validate

aggregate:
	uv run python main.py --aggregate-only

reports:
	uv run python -m scanner.compute
	uv run python -m scanner.reports

pipeline:
	uv run python main.py
