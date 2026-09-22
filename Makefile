# ReportSmith — the authoritative task list. CI runs these targets.
#
# There is no `make` on the development box this was built on (BLOCKERS B1), so `make.ps1`
# mirrors every target for Windows. A test asserts the two expose the same set, because a
# parity claim nobody checks stops being true in about a week.

PY      := backend/.venv/Scripts/python.exe
PYX     := $(shell test -x $(PY) && echo $(PY) || echo python)
BACKEND := cd backend &&
WEB     := cd frontend &&

.DEFAULT_GOAL := help
.PHONY: help install dev dev-api dev-web up down demo month1 month2 diff fixtures golden \
        test test-fast test-live lint fmt typecheck evals evals-gate clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (npm) dependencies
	$(BACKEND) uv venv && uv pip install -e ".[dev]"
	$(WEB) npm install

dev: ## Run the API and the SPA together — the demo entrypoint
	@echo "API  → http://localhost:8000/docs"
	@echo "SPA  → http://localhost:5173"
	@($(BACKEND) $(PYX) -m uvicorn app.main:app --reload --port 8000 &) ; $(WEB) npm run dev

dev-api: ## Run the FastAPI backend with reload
	$(BACKEND) $(PYX) -m uvicorn app.main:app --reload --port 8000

dev-web: ## Run the Vite dev server
	$(WEB) npm run dev

up: dev ## Alias for dev (spec 00 A1)

down: ## Stop docker compose
	docker compose down

demo: ## Both periods end to end, then the month diff — the launch clip
	$(BACKEND) $(PYX) -m app.cli demo

month1: ## Assemble, approve, waive, sign and archive the first period
	$(BACKEND) $(PYX) -m app.cli month1

month2: ## The same template on the NEXT period — spec 13 F7
	$(BACKEND) $(PYX) -m app.cli month2

diff: ## Show the month-diff verdict for the two most recent packs
	$(BACKEND) $(PYX) -m app.cli demo

fixtures: ## Regenerate the SpendSort export fixtures by RUNNING SpendSort
	$(PYX) fixtures/gen_fixtures.py

capture: ## Screenshot + VERIFY all six screens headless (needs `make dev` running)
	$(WEB) node capture.mjs

record: ## Record docs/demo.webm by driving the real app (needs `make dev` running)
	$(WEB) node record-demo.mjs

golden: ## Regenerate the committed golden assembly files
	$(PYX) evals/make_golden.py

test: lint typecheck ## Lint, typecheck, then the full suite (LLM mocked; no key, no spend)
	$(BACKEND) $(PYX) -m pytest -q -m "not live"
	$(WEB) npm run test

test-fast: ## Tests only, no lint or typecheck
	$(BACKEND) $(PYX) -m pytest -q -m "not live"

test-live: ## Tests that hit a real model (needs OPENAI_API_KEY; costs money)
	$(BACKEND) REPORTSMITH_LLM=live $(PYX) -m pytest -q -m live

lint: ## ruff check
	$(BACKEND) $(PYX) -m ruff check app tests
	$(BACKEND) $(PYX) -m ruff check numcheck

fmt: ## ruff format (writes)
	$(BACKEND) $(PYX) -m ruff format app tests numcheck

typecheck: ## mypy (backend) + tsc (frontend)
	$(BACKEND) $(PYX) -m mypy app
	$(WEB) npm run typecheck

evals: ## Run the three gates and print their reports
	$(PYX) evals/run_fidelity.py
	$(PYX) evals/run_e2e.py

evals-gate: ## What CI runs: the gates, plus the self-test that proves they can fail
	$(PYX) evals/run_fidelity.py
	$(PYX) evals/run_fidelity.py --self-test
	$(PYX) evals/run_e2e.py
	$(BACKEND) $(PYX) -m pytest -q tests/test_state_machine.py tests/test_no_silent_omission.py

clean: ## Remove the local DB, caches and build output
	rm -rf backend/reportsmith.db archive frontend/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
