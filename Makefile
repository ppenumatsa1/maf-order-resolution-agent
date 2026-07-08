SHELL := /bin/bash
COMPOSE_ENV_FILE ?= backend/.env

.PHONY: help bootstrap venv-backend install-backend install-frontend ensure-backend-env \
	run-backend run-frontend format lint test test-backend eval-backend test-e2e manual-matrix \
	parity-all run-mock-mcp up down logs ps docker-test \
	validate-quick validate-full deploy-app deploy-full clean \
	foundry-up foundry-provision foundry-deploy foundry-smoke foundry-access-path foundry-sync-env

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
	@echo "  foundry-sync-env - Sync infra/foundry-hosted/runtime/.env into current azd env"
	@echo "  foundry-smoke   - Invoke hosted agent health check via invocations protocol"
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
				echo "Using host Azure CLI token for Foundry hosted invocations."; \
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
	cd infra/foundry-hosted && azd up --no-prompt

foundry-provision:
	cd infra/foundry-hosted && azd provision --no-prompt

foundry-deploy:
	cd infra/foundry-hosted && azd deploy order-resolution-hosted --no-prompt

foundry-sync-env:
	@set -euo pipefail; \
	cd infra/foundry-hosted; \
	if [[ ! -f runtime/.env ]]; then \
		echo "Missing infra/foundry-hosted/runtime/.env"; \
		exit 1; \
	fi; \
	appinsights_line="$$(grep -E '^APPLICATIONINSIGHTS_CONNECTION_STRING=' runtime/.env || true)"; \
	if [[ -z "$$appinsights_line" || "$$appinsights_line" == 'APPLICATIONINSIGHTS_CONNECTION_STRING=' ]]; then \
		echo "APPLICATIONINSIGHTS_CONNECTION_STRING must be set in infra/foundry-hosted/runtime/.env"; \
		exit 1; \
	fi; \
	cp runtime/.env agent/runtime/.env; \
	cp runtime/.env ../../backend/foundry/runtime/.env; \
	echo "derived agent/runtime/.env and backend/foundry/runtime/.env from runtime/.env"; \
	while IFS= read -r line; do \
		[[ -z "$$line" || "$$line" =~ ^[[:space:]]*# ]] && continue; \
		key="$${line%%=*}"; \
		value="$${line#*=}"; \
		azd env set "$$key" "$$value" >/dev/null; \
		echo "synced $$key"; \
	done < runtime/.env

foundry-smoke:
	cd infra/foundry-hosted && azd ai agent invoke order-resolution-hosted '{"message":"health check"}' --protocol invocations --no-prompt

foundry-access-path:
	cd infra/foundry-hosted && az deployment group create \
		--resource-group "$${FOUNDRY_ACCESS_RG:-rg-maf-ora-ni-eus-07080910}" \
		--template-file iac/access-path.bicep \
		--parameters @iac/access-path.parameters.json \
		--parameters runnerVmSshPublicKey="$$(cat "$${RUNNER_SSH_PUBKEY_PATH:-$$HOME/.ssh/id_rsa.pub}")"

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf backend/.pytest_cache scripts/playwright/test-results scripts/playwright/playwright-report
