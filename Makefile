SHELL := /bin/bash

.PHONY: help bootstrap venv-backend install-backend install-frontend ensure-backend-env \
	run-backend run-frontend format lint test test-backend eval-backend test-e2e manual-matrix \
	run-mock-mcp up down logs ps docker-test clean

help:
	@echo "Available targets:"
	@echo "  up              - Start all servers with Docker (backend, frontend, mock-mcp)"
	@echo "  down            - Stop all Docker servers"
	@echo "  logs            - Tail Docker logs"
	@echo "  ps              - Show running Docker services"
	@echo "  bootstrap       - Create backend venv + install backend/frontend/playwright deps"
	@echo "  run-backend     - Start FastAPI backend locally on :8000"
	@echo "  run-frontend    - Start Vite frontend locally on :5173"
	@echo "  format          - Format Python files (ruff format)"
	@echo "  lint            - Lint Python files (ruff check)"
	@echo "  test            - Run lint + backend tests"
	@echo "  test-backend    - Run backend pytest suite"
	@echo "  eval-backend    - Run workflow eval harness"
	@echo "  test-e2e        - Run Playwright tests locally"
	@echo "  manual-matrix   - Run ORD-1001..ORD-1010 manual verification matrix"
	@echo "  run-mock-mcp    - Start local authenticated MCP simulator"
	@echo "  docker-test     - Run Playwright tests in Docker compose profile"
	@echo "  clean           - Remove caches and test artifacts"

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

run-backend: ensure-backend-env
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && npm run dev

format: ensure-backend-env
	cd backend && . .venv/bin/activate && ruff format .

lint: ensure-backend-env
	cd backend && . .venv/bin/activate && ruff check .

test: lint test-backend

test-backend: ensure-backend-env
	cd backend && . .venv/bin/activate && pytest -q

eval-backend: ensure-backend-env
	cd backend && . .venv/bin/activate && python -m evals.eval_runner

test-e2e:
	@if [[ -n "$${PLAYWRIGHT_BASE_URL:-}" ]]; then \
		cd scripts/playwright && npm run test:e2e; \
	else \
		frontend_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
		frontend_url="http://127.0.0.1:$${frontend_port}"; \
		(cd frontend && node_modules/.bin/vite --host 127.0.0.1 --port "$${frontend_port}" --strictPort) > "/tmp/maf-frontend-e2e-$${frontend_port}.log" 2>&1 & \
		frontend_pid="$$!"; \
		trap 'kill '"$$frontend_pid"' 2>/dev/null || true; wait '"$$frontend_pid"' 2>/dev/null || true' EXIT; \
		for _ in {1..30}; do \
			curl -fsS "$${frontend_url}" >/dev/null && break; \
			sleep 1; \
		done; \
		PLAYWRIGHT_BASE_URL="$${frontend_url}" bash -c 'cd scripts/playwright && npm run test:e2e'; \
	fi

manual-matrix:
	scripts/manual/run-manual-matrix.sh "$${API_URL:-http://localhost:8000}" $${MANUAL_MATRIX_ARGS:-}

run-mock-mcp: ensure-backend-env
	. backend/.venv/bin/activate && uvicorn scripts.mcp.mock_mcp_server:app --reload --port 8011

up:
	docker compose up --build -d backend frontend mock-mcp
	@echo "Frontend: http://localhost:5173"
	@echo "Backend health: http://localhost:8000/health"

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

docker-test:
	docker compose --profile test up --build --abort-on-container-exit playwright

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf backend/.pytest_cache scripts/playwright/test-results scripts/playwright/playwright-report
