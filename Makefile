SHELL := /bin/bash
COMPOSE_ENV_FILE ?= backend/.env.example

.PHONY: help bootstrap venv-backend install-backend install-frontend ensure-backend-env ensure-test-postgres \
	run-backend run-frontend format lint test test-backend eval-backend eval-foundry eval-all test-e2e manual-matrix \
	parity-all run-mock-mcp up down logs ps docker-test validate-quick validate-full deploy-app deploy-full clean

help:
	@echo "Available targets:"
	@echo "  up/down/logs/ps  - Manage the local Docker parity stack"
	@echo "  bootstrap        - Install backend, frontend, and Playwright dependencies"
	@echo "  test             - Run backend lint and tests"
	@echo "  eval-backend     - Run deterministic workflow contract evaluation"
	@echo "  eval-foundry     - Run report-only Foundry low/high-risk evaluation"
	@echo "  test-e2e         - Run local Playwright tests"
	@echo "  docker-test      - Run Playwright against Docker Compose"
	@echo "  parity-all       - Run fast local and Azure app-hosted parity checks"

bootstrap: install-backend install-frontend

venv-backend:
	cd backend && python3 -m venv .venv

install-backend: venv-backend
	cd backend && . .venv/bin/activate && pip install -r requirements-dev.txt

install-frontend:
	cd frontend && npm install
	cd scripts/playwright && npm install

ensure-backend-env:
	test -d backend/.venv || $(MAKE) venv-backend
	. backend/.venv/bin/activate && python -c "import pytest" >/dev/null 2>&1 || $(MAKE) install-backend

ensure-test-postgres:
	@DATABASE_URL="$${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable}" \
		./scripts/local/ensure_test_postgres.sh

run-backend: ensure-backend-env
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && npm run dev

format: ensure-backend-env
	cd backend && . .venv/bin/activate && ruff format .

lint: ensure-backend-env
	cd backend && . .venv/bin/activate && ruff check .

test: lint test-backend

test-backend: ensure-backend-env ensure-test-postgres
	cd backend && . .venv/bin/activate && pytest -q

eval-backend: ensure-backend-env ensure-test-postgres
	cd backend && . .venv/bin/activate && python -m evals.eval_runner

eval-foundry: ensure-backend-env
	cd backend && . .venv/bin/activate && python -m evals.foundry_eval_runner

eval-all: eval-backend eval-foundry

test-e2e:
	@if [[ -n "$${PLAYWRIGHT_BASE_URL:-}" ]]; then \
		cd scripts/playwright && npm run test:e2e; \
	else \
		health_json="$$(curl -fsS http://localhost:8000/api/health 2>/dev/null || true)"; \
		if [[ -z "$$health_json" || "$$health_json" != *'"workflow_mode":"maf_sdk"'* ]]; then \
			$(MAKE) COMPOSE_ENV_FILE=backend/.env.example up; \
		fi; \
		frontend_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
		frontend_url="http://127.0.0.1:$${frontend_port}"; \
		(cd frontend && node_modules/.bin/vite --host 127.0.0.1 --port "$${frontend_port}" --strictPort) > "/tmp/maf-frontend-e2e-$${frontend_port}.log" 2>&1 & \
		frontend_pid="$$!"; \
		trap 'kill '"$$frontend_pid"' 2>/dev/null || true; wait '"$$frontend_pid"' 2>/dev/null || true' EXIT; \
		for _ in {1..30}; do curl -fsS "$${frontend_url}" >/dev/null && break; sleep 1; done; \
		PLAYWRIGHT_BASE_URL="$${frontend_url}" bash -c 'cd scripts/playwright && npm run test:e2e'; \
	fi

manual-matrix:
	scripts/manual/run-manual-matrix.sh "$${API_URL:-http://localhost:8000}" $${MANUAL_MATRIX_ARGS:-}

parity-all:
	scripts/parity/run-parity-matrix.sh --targets local azure --profile fast

run-mock-mcp: ensure-backend-env
	. backend/.venv/bin/activate && uvicorn scripts.mcp.mock_mcp_server:app --reload --port 8011

up:
	docker compose --env-file $(COMPOSE_ENV_FILE) up --build -d backend frontend mock-mcp
	@echo "Frontend: http://localhost:5173"
	@echo "Backend health: http://localhost:8000/health"

down:
	docker compose --env-file $(COMPOSE_ENV_FILE) down --remove-orphans

logs:
	docker compose --env-file $(COMPOSE_ENV_FILE) logs -f --tail=200

ps:
	docker compose --env-file $(COMPOSE_ENV_FILE) ps

docker-test:
	POSTGRES_PORT="$${POSTGRES_PORT:-5433}" MOCK_MCP_PORT="$${MOCK_MCP_PORT:-8012}" BACKEND_PORT="$${BACKEND_PORT:-8002}" FRONTEND_PORT="$${FRONTEND_PORT:-5174}" docker compose --env-file $(COMPOSE_ENV_FILE) --profile test up --build --abort-on-container-exit playwright

validate-quick:
	@if [[ -n "$${PLAYWRIGHT_BASE_URL:-}" ]]; then $(MAKE) test-e2e; \
	elif [[ -n "$${WEB_URL:-}" ]]; then PLAYWRIGHT_BASE_URL="$${WEB_URL}" $(MAKE) test-e2e; \
	else $(MAKE) test-e2e; fi
	@if [[ -n "$${API_URL:-}" ]]; then infra/azure-apphosted/runtime/smoke-test.sh "$${API_URL}" "$${WEB_URL:-}"; fi

validate-full:
	$(MAKE) test
	$(MAKE) eval-backend
	$(MAKE) test-e2e
	./scripts/skills/design-review-skill.sh

deploy-app:
	azd deploy

deploy-full:
	azd provision
	azd deploy

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf backend/.pytest_cache scripts/playwright/test-results scripts/playwright/playwright-report
