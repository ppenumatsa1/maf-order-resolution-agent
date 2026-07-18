SHELL := /bin/bash
COMPOSE_ENV_FILE ?= backend/.env

.PHONY: help bootstrap venv-backend install-backend install-frontend ensure-backend-env ensure-test-postgres \
	run-backend run-frontend format lint test test-backend eval-backend eval-foundry eval-all test-e2e manual-matrix \
	parity-all run-mock-mcp up down logs ps docker-test \
	validate-quick validate-full deploy-app deploy-full clean \
	foundry-up foundry-provision foundry-deploy foundry-smoke foundry-access-path

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
	@echo "  eval-backend    - Run deterministic workflow contract eval harness"
	@echo "  eval-foundry    - Run report-only Foundry evaluator run"
	@echo "  eval-all        - Run deterministic and Foundry evals"
	@echo "  test-e2e        - Run Playwright tests locally"
	@echo "  manual-matrix   - Run ORD-1001..ORD-1010 manual verification matrix"
	@echo "  parity-all      - Run fast parity gate across local + Azure + Foundry"
	@echo "  run-mock-mcp    - Start local authenticated MCP simulator"
	@echo "  docker-test     - Run Playwright tests in Docker compose profile"
	@echo "  validate-quick  - Fast redeploy validation (Playwright + smoke if API_URL set)"
	@echo "  validate-full   - Full validation (test + eval + e2e + design-review)"
	@echo "  deploy-app      - App-only Azure deploy (azd deploy)"
	@echo "  deploy-full     - Infra + app Azure deploy (azd provision && azd deploy)"
	@echo "  foundry-up      - Self-contained Foundry hosted-agent azd up (BYO VNET + private deps)"
	@echo "  foundry-provision - Provision self-contained Foundry hosted-agent infra only"
	@echo "  foundry-deploy  - Deploy hosted agent to Foundry (after provision/up)"
	@echo "  foundry-smoke   - Invoke hosted agent health check via responses protocol"
	@echo "  foundry-access-path - Deploy private runner/Bastion access path via Bicep"
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

ensure-test-postgres:
	@DATABASE_URL="$${DATABASE_URL:-$${FOUNDRY_RUNTIME_DATABASE_URL:-$${RUNTIME_DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable}}}" \
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
			echo "Ensuring deterministic local backend for E2E (WORKFLOW_MODE=maf_sdk)."; \
			$(MAKE) COMPOSE_ENV_FILE=backend/.env up; \
		fi; \
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

parity-all:
	scripts/parity/run-parity-matrix.sh --targets local azure foundry --profile fast

run-mock-mcp: ensure-backend-env
	. backend/.venv/bin/activate && uvicorn scripts.mcp.mock_mcp_server:app --reload --port 8011

up:
	@set -euo pipefail; \
	workflow_mode="$$(grep -E '^[[:space:]]*WORKFLOW_MODE=' $(COMPOSE_ENV_FILE) | tail -1 | cut -d= -f2- | tr -d '"' || true)"; \
	hosted_key="$$(grep -E '^[[:space:]]*FOUNDRY_HOSTED_API_KEY=' $(COMPOSE_ENV_FILE) | tail -1 | cut -d= -f2- | tr -d '"' || true)"; \
	if [[ "$$workflow_mode" == "foundry_hosted" && -z "$$hosted_key" ]]; then \
		if command -v az >/dev/null 2>&1; then \
			token="$$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv 2>/dev/null || true)"; \
			if [[ -n "$$token" ]]; then \
				echo "Using host Azure CLI token for Foundry hosted responses."; \
				FOUNDRY_HOSTED_API_KEY="Bearer $$token" docker compose --env-file $(COMPOSE_ENV_FILE) up --build -d backend frontend mock-mcp; \
			else \
				echo "WARN: Could not acquire Azure CLI token. Set FOUNDRY_HOSTED_API_KEY in $(COMPOSE_ENV_FILE)."; \
				docker compose --env-file $(COMPOSE_ENV_FILE) up --build -d backend frontend mock-mcp; \
			fi; \
		else \
			echo "WARN: Azure CLI not found on host. Set FOUNDRY_HOSTED_API_KEY in $(COMPOSE_ENV_FILE)."; \
			docker compose --env-file $(COMPOSE_ENV_FILE) up --build -d backend frontend mock-mcp; \
		fi; \
	else \
		docker compose --env-file $(COMPOSE_ENV_FILE) up --build -d backend frontend mock-mcp; \
	fi
	@echo "Frontend: http://localhost:5173"
	@echo "Backend health: http://localhost:8000/health"

down:
	docker compose --env-file $(COMPOSE_ENV_FILE) down --remove-orphans

logs:
	docker compose --env-file $(COMPOSE_ENV_FILE) logs -f --tail=200

ps:
	docker compose --env-file $(COMPOSE_ENV_FILE) ps

docker-test:
	docker compose --env-file $(COMPOSE_ENV_FILE) --profile test up --build --abort-on-container-exit playwright

validate-quick:
	@if [[ -n "$${PLAYWRIGHT_BASE_URL:-}" ]]; then \
		$(MAKE) test-e2e; \
	elif [[ -n "$${WEB_URL:-}" ]]; then \
		PLAYWRIGHT_BASE_URL="$${WEB_URL}" $(MAKE) test-e2e; \
	else \
		$(MAKE) test-e2e; \
	fi
	@if [[ -n "$${API_URL:-}" ]]; then \
		infra/azure-apphosted/runtime/smoke-test.sh "$${API_URL}" "$${WEB_URL:-}"; \
	fi

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

foundry-up:
	./scripts/foundry/ensure_foundry_azd_defaults.sh
	cd infra/foundry-hosted && azd up --no-prompt

foundry-provision:
	./scripts/foundry/ensure_foundry_azd_defaults.sh
	cd infra/foundry-hosted && azd provision --no-prompt $(if $(FOUNDRY_PROVISION_NO_STATE),--no-state,)

foundry-deploy:
	@test -f backend/agent.yaml
	@test -f backend/foundry/main.py
	@./scripts/foundry/sync_hosted_source.sh
	@agent_name="$${FOUNDRY_HOSTED_AGENT_NAME:-order-resolution-hosted}"; \
	cd infra/foundry-hosted && azd deploy "$$agent_name" --no-prompt --timeout "$${FOUNDRY_DEPLOY_TIMEOUT_SECONDS:-1800}" && \
	azd ai agent show "$$agent_name" --output json --no-prompt >/dev/null

foundry-smoke:
	@if [[ -n "$${SMOKE_THREAD_ID:-}" ]]; then \
		cd infra/foundry-hosted && azd ai agent invoke order-resolution-hosted "$${SMOKE_MESSAGE:-Resolve delayed order ORD-1009}" --protocol responses --conversation-id "$${SMOKE_THREAD_ID}" --no-prompt; \
	else \
		cd infra/foundry-hosted && azd ai agent invoke order-resolution-hosted "$${SMOKE_MESSAGE:-Resolve delayed order ORD-1009}" --protocol responses --new-conversation --new-session --no-prompt; \
	fi

foundry-access-path:
	cd infra/foundry-hosted && az deployment group create \
		--resource-group "$${FOUNDRY_ACCESS_RG:-rg-maf-ora-ni-eus-07080910}" \
		--template-file iac/access-path.bicep \
		--parameters @iac/access-path.parameters.json \
		--parameters runnerVmSshPublicKey="$$(cat "$${RUNNER_SSH_PUBKEY_PATH:-$$HOME/.ssh/id_rsa.pub}")"

foundry-postgres-readiness:
	./scripts/foundry/check_public_postgres_readiness.sh

foundry-deploy-public:
	./scripts/foundry/deploy_public_dev.sh

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf backend/.pytest_cache scripts/playwright/test-results scripts/playwright/playwright-report
