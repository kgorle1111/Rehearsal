.PHONY: check test lint types evals

check: lint types test evals

lint:
	uv run ruff check .

types:
	uv run mypy .

test:
	uv run pytest

evals:
	uv run rehearsal-evals run --eval EV-00
	@echo "--- SKIPPED / BLOCKED-ON-HUMAN or BLOCKED-ON-HARDWARE (see notes) ---"
	uv run rehearsal-evals run --eval EV-01
	uv run rehearsal-evals run --eval EV-02
	uv run rehearsal-evals run --eval EV-03
	uv run rehearsal-evals run --eval EV-05
	uv run rehearsal-evals run --eval EV-07
	uv run rehearsal-evals run --eval EV-08
