.DEFAULT_GOAL := help
SHELL := /bin/bash

# ─── Environment ──────────────────────────────────────────────────────────────

.PHONY: install
install: ## Install all dependencies (Python + frontend)
	uv venv
	uv pip install -e ".[dev]"
	cd frontend && npm install

.PHONY: models
models: ## Download and verify the model set
	python -m rehearsal.tools.fetch_models --verify

.PHONY: smoke-models
smoke-models: ## One inference per model; prints latency. MUST pass before building.
	python -m rehearsal.tools.smoke_models

# ─── Data ─────────────────────────────────────────────────────────────────────

.PHONY: scenarios
scenarios: ## Build the scenario bank from configured sources
	python -m rehearsal.data.build_scenarios

.PHONY: label-sheet
label-sheet: ## Generate a blank calibration label sheet (see SETUP.md section 6)
	python -m rehearsal.tools.make_label_sheet --out data/calibration/worksheet.md

.PHONY: split-calibration
split-calibration: ## Split labelled items into dev(25)/test(15). Run ONCE, before any tuning.
	python -m rehearsal.tools.split_calibration --dev 25 --test 15 --seal

# ─── Running ──────────────────────────────────────────────────────────────────

.PHONY: dev
dev: ## Backend + frontend with hot reload
	@trap 'kill 0' EXIT; \
	uvicorn rehearsal.api.app:app --reload --port 8000 & \
	cd frontend && npm run dev & \
	wait

.PHONY: session
session: ## Run one practice session end-to-end from the CLI
	python -m rehearsal.cli session

.PHONY: report
report: ## Render the most recent session report
	python -m rehearsal.cli report --last

# ─── Quality ──────────────────────────────────────────────────────────────────

.PHONY: lint
lint: ## ruff + format check
	ruff check .
	ruff format --check .

.PHONY: types
types: ## Static type check
	mypy rehearsal

.PHONY: test
test: ## Unit, property and contract tests
	pytest -q

.PHONY: evals
evals: ## Full eval suite; diffs results against plans/metrics-snapshot.md
	python -m rehearsal.evals.run_all --diff-snapshot plans/metrics-snapshot.md

.PHONY: calibrate
calibrate: ## Score the grader against human labels; writes the calibration report
	python -m rehearsal.evals.calibrate --dev data/calibration/dev.jsonl \
	                                    --test data/calibration/test.jsonl

.PHONY: leakage-test
leakage-test: ## The information-isolation A/B (see docs/08-evals.md)
	python -m rehearsal.evals.leakage_ab

.PHONY: latency
latency: ## Real-time budget conformance (see docs/05-voice-pipeline.md)
	python -m rehearsal.evals.latency

.PHONY: a11y
a11y: ## Automated accessibility scan + keyboard path check
	cd frontend && npm run test:a11y

.PHONY: check
check: lint types test evals ## The pre-commit gate — everything must be green
	@echo "✓ all checks passed"

# ─── Housekeeping ─────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove caches and build artefacts (never touches data/)
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build frontend/dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
