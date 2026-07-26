.PHONY: check test lint types evals

check: lint types test evals

lint:
	uv run ruff check .

types:
	uv run mypy .

test:
	uv run pytest

evals:
	@echo "evals: stub — no fixtures wired up yet"
