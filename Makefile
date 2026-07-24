SHELL := /bin/bash
COMPOSE_ENV_FILE ?= backend/.env

.PHONY: help bootstrap venv-backend install-backend install-frontend ensure-backend-env ensure-test-postgres \
	run-backend run-frontend format lint test test-backend eval-backend eval-foundry eval-all test-e2e manual-matrix \
	parity-all run-mock-mcp up down logs ps docker-test \
	validate-quick validate-full clean \
	foundry-up foundry-preflight foundry-provision-preview foundry-provision foundry-deploy foundry-hosted-refresh \
	foundry-app-deploy foundry-connectivity-proof foundry-postgres-lockdown foundry-evidence foundry-release foundry-smoke foundry-access-path

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
	@echo "  foundry-up      - Self-contained Foundry hosted-agent azd up (BYO VNET + private deps)"
	@echo "  foundry-preflight - Verify private release inputs without changing Azure"
	@echo "  foundry-provision-preview - Preview private infrastructure changes without applying them"
	@echo "  foundry-provision - Provision self-contained Foundry hosted-agent infra only"
	@echo "  foundry-deploy  - Deploy hosted agent to Foundry (after provision/up)"
	@echo "  foundry-hosted-refresh - Optionally refresh the hosted agent (FOUNDRY_REFRESH_HOSTED_AGENT=true)"
	@echo "  foundry-app-deploy - Deploy private backend and public frontend Container Apps"
	@echo "  foundry-connectivity-proof - Record ACA and hosted-agent PostgreSQL connectivity proof"
	@echo "  foundry-postgres-lockdown - Disable PostgreSQL public access using recorded connectivity proof"
	@echo "  foundry-evidence - Collect hosted E2E, evaluation, and telemetry evidence"
	@echo "  foundry-release - Preflight, provision, deploy apps, optional agent refresh, proof, lockdown, evidence"
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
	cd backend && . .venv/bin/activate && \
		foundry_env_file="../infra/foundry-hosted/.azure/$${FOUNDRY_AZD_ENV_NAME:-foundry-private-env}/.env"; \
		if [[ -f "$$foundry_env_file" ]]; then \
			set -a; . "$$foundry_env_file"; set +a; \
		fi; \
		if [[ -z "$${FOUNDRY_PROJECTS_ENDPOINT:-}" && -n "$${FOUNDRY_PROJECT_ENDPOINT:-}" ]]; then \
			export FOUNDRY_PROJECTS_ENDPOINT="$$FOUNDRY_PROJECT_ENDPOINT"; \
		fi; \
		if [[ -z "$${FOUNDRY_MODEL_DEPLOYMENT_NAME:-}" && -n "$${AZURE_AI_MODEL_DEPLOYMENT_NAME:-}" ]]; then \
			export FOUNDRY_MODEL_DEPLOYMENT_NAME="$$AZURE_AI_MODEL_DEPLOYMENT_NAME"; \
		fi; \
		python -m evals.foundry_eval_runner

eval-all: eval-backend eval-foundry

test-e2e:
	@if [[ -n "$${PLAYWRIGHT_BASE_URL:-}" ]]; then \
		cd scripts/playwright && npm run test:e2e; \
	else \
		$(MAKE) ensure-backend-env ensure-test-postgres; \
		backend_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
		backend_url="http://127.0.0.1:$${backend_port}"; \
		backend_log="/tmp/maf-backend-e2e-$${backend_port}.log"; \
		( \
			cd backend && . .venv/bin/activate && \
			APP_ENV=local \
			WORKFLOW_MODE=maf_sdk \
			STORE_PROVIDER=postgres \
			RAG_PROVIDER=pgvector \
			MEMORY_PROVIDER=postgres \
			MCP_SERVER_URL= \
			uvicorn app.main:app --host 127.0.0.1 --port "$${backend_port}" \
		) > "$${backend_log}" 2>&1 & \
		backend_pid="$$!"; \
		disown "$${backend_pid}" 2>/dev/null || true; \
		frontend_pid=""; \
		frontend_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
		frontend_url="http://127.0.0.1:$${frontend_port}"; \
		frontend_log="/tmp/maf-frontend-e2e-$${frontend_port}.log"; \
		trap 'kill "${backend_pid:-}" 2>/dev/null || true; kill "${frontend_pid:-}" 2>/dev/null || true' EXIT; \
		for _ in {1..45}; do \
			health_json="$$(curl -fsS "$${backend_url}/api/health" 2>/dev/null || true)"; \
			if [[ "$${health_json}" == *'"workflow_mode":"maf_sdk"'* ]]; then \
				break; \
			fi; \
			sleep 1; \
		done; \
		health_json="$$(curl -fsS "$${backend_url}/api/health" 2>/dev/null || true)"; \
		if [[ "$${health_json}" != *'"workflow_mode":"maf_sdk"'* ]]; then \
			echo "Backend failed to become ready for E2E. See $${backend_log}"; \
			exit 1; \
		fi; \
		(cd frontend && VITE_PROXY_TARGET="$${backend_url}" node_modules/.bin/vite --host 127.0.0.1 --port "$${frontend_port}" --strictPort) > "$${frontend_log}" 2>&1 & \
		frontend_pid="$$!"; \
		disown "$${frontend_pid}" 2>/dev/null || true; \
		for _ in {1..30}; do \
			curl -fsS "$${frontend_url}" >/dev/null && break; \
			sleep 1; \
		done; \
		proxy_health="$$(curl -fsS "$${frontend_url}/api/health" 2>/dev/null || true)"; \
		if [[ "$${proxy_health}" != *'"workflow_mode":"maf_sdk"'* || "$${proxy_health}" != *'"environment":"local"'* ]]; then \
			echo "Frontend proxy is not targeting the isolated local backend. See $${frontend_log}"; \
			exit 1; \
		fi; \
		cd scripts/playwright && PLAYWRIGHT_BASE_URL="$${frontend_url}" npm run test:e2e; \
		e2e_status="$$?"; \
		kill "$${backend_pid}" "$${frontend_pid}" 2>/dev/null || true; \
		wait "$${backend_pid}" 2>/dev/null || true; \
		wait "$${frontend_pid}" 2>/dev/null || true; \
		exit "$${e2e_status}"; \
	fi

manual-matrix:
	scripts/manual/run-manual-matrix.sh "$${API_URL:-http://localhost:8000}" $${MANUAL_MATRIX_ARGS:-}

parity-all:
	scripts/parity/run-parity-matrix.sh --targets local foundry --profile fast

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
	@set -euo pipefail; \
	project="maf-order-resolution-agent-test"; \
	backend_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
	frontend_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
	postgres_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
	mcp_port="$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"; \
	trap 'docker compose -p "$$project" --env-file $(COMPOSE_ENV_FILE) --profile test down --volumes --remove-orphans >/dev/null 2>&1 || true' EXIT; \
	BACKEND_PORT="$$backend_port" FRONTEND_PORT="$$frontend_port" POSTGRES_PORT="$$postgres_port" MCP_PORT="$$mcp_port" \
		docker compose -p "$$project" --env-file $(COMPOSE_ENV_FILE) --profile test up --build --abort-on-container-exit playwright

validate-quick:
	@if [[ -n "$${PLAYWRIGHT_BASE_URL:-}" ]]; then \
		$(MAKE) test-e2e; \
	elif [[ -n "$${WEB_URL:-}" ]]; then \
		PLAYWRIGHT_BASE_URL="$${WEB_URL}" $(MAKE) test-e2e; \
	else \
		$(MAKE) test-e2e; \
	fi
	@true

validate-full:
	$(MAKE) test
	$(MAKE) eval-backend
	$(MAKE) test-e2e
	./scripts/skills/design-review-skill.sh

foundry-up:
	./scripts/foundry/ensure_foundry_azd_defaults.sh
	cd infra/foundry-hosted && azd up --no-prompt

foundry-preflight:
	./scripts/foundry/preflight_private_release.sh

foundry-provision-preview: foundry-preflight
	./scripts/foundry/ensure_foundry_azd_defaults.sh
	cd infra/foundry-hosted && azd provision --preview --no-prompt $(if $(FOUNDRY_PROVISION_NO_STATE),--no-state,)

foundry-provision:
	$(MAKE) foundry-preflight
	./scripts/foundry/ensure_foundry_azd_defaults.sh
	cd infra/foundry-hosted && azd provision --no-prompt $(if $(FOUNDRY_PROVISION_NO_STATE),--no-state,)

foundry-deploy:
	@test -f backend/agent.yaml
	@test -f backend/foundry/main.py
	@./scripts/foundry/sync_hosted_source.sh
	@agent_name="$${FOUNDRY_HOSTED_AGENT_NAME:-order-resolution-hosted}"; \
	cd infra/foundry-hosted && \
	set -a && eval "$$(azd env get-values)" && set +a && \
	azd deploy "$$agent_name" --no-prompt --timeout "$${FOUNDRY_DEPLOY_TIMEOUT_SECONDS:-1800}" && \
	azd ai agent show "$$agent_name" --output json --no-prompt >/dev/null

foundry-app-deploy:
	@test -f backend/Dockerfile
	@test -f frontend/Dockerfile
	cd infra/foundry-hosted && azd deploy backend --no-prompt
	cd infra/foundry-hosted && azd deploy frontend --no-prompt

foundry-hosted-refresh:
	@if [[ "$${FOUNDRY_REFRESH_HOSTED_AGENT:-false}" == "true" ]]; then \
		$(MAKE) foundry-deploy; \
	else \
		echo "Skipping hosted-agent refresh (set FOUNDRY_REFRESH_HOSTED_AGENT=true to deploy it)."; \
	fi

foundry-connectivity-proof:
	./scripts/foundry/verify_private_connectivity.sh

foundry-postgres-lockdown:
	@set -euo pipefail; \
	cd infra/foundry-hosted && \
	resource_group="$${FOUNDRY_RESOURCE_GROUP:-$${AZURE_RESOURCE_GROUP:-$$(azd env get-value AZURE_RESOURCE_GROUP)}}"; \
	postgres_server="$${POSTGRES_SERVER_NAME:-$$(azd env get-value POSTGRES_SERVER_NAME 2>/dev/null || true)}"; \
	postgres_fqdn="$${POSTGRES_SERVER_FQDN:-$$(azd env get-value POSTGRES_SERVER_FQDN 2>/dev/null || true)}"; \
	private_endpoint="$${POSTGRES_PRIVATE_ENDPOINT_NAME:-$$(azd env get-value POSTGRES_PRIVATE_ENDPOINT_NAME 2>/dev/null || true)}"; \
	private_dns_zone="$${POSTGRES_PRIVATE_DNS_ZONE_NAME:-$$(azd env get-value POSTGRES_PRIVATE_DNS_ZONE_NAME 2>/dev/null || true)}"; \
	AZURE_RESOURCE_GROUP="$$resource_group" \
	POSTGRES_SERVER_NAME="$$postgres_server" \
	POSTGRES_SERVER_FQDN="$$postgres_fqdn" \
	POSTGRES_PRIVATE_ENDPOINT_NAME="$$private_endpoint" \
	POSTGRES_PRIVATE_DNS_ZONE_NAME="$$private_dns_zone" \
	POSTGRES_CONNECTIVITY_EVIDENCE_FILE="$${POSTGRES_CONNECTIVITY_EVIDENCE_FILE:-../../backend/.foundry/results/private-connectivity-proof.json}" \
	"../../scripts/foundry/harden_postgres_private_access.sh"

foundry-evidence:
	./scripts/foundry/collect_private_release_evidence.sh

foundry-release:
	$(MAKE) validate-full
	$(MAKE) foundry-provision-preview
	$(MAKE) foundry-provision
	$(MAKE) foundry-app-deploy
	$(MAKE) foundry-hosted-refresh
	$(MAKE) foundry-connectivity-proof
	$(MAKE) foundry-postgres-lockdown
	$(MAKE) foundry-evidence

foundry-smoke:
	@set -euo pipefail; \
	message="$${SMOKE_MESSAGE:-Resolve delayed order ORD-1009}"; \
	attempt=1; \
	max_attempts="$${SMOKE_MAX_ATTEMPTS:-6}"; \
	while [[ "$$attempt" -le "$$max_attempts" ]]; do \
		set +e; \
		if [[ -n "$${SMOKE_THREAD_ID:-}" ]]; then \
			output="$$(cd infra/foundry-hosted && azd ai agent invoke order-resolution-hosted "$$message" --protocol responses --conversation-id "$${SMOKE_THREAD_ID}" --no-prompt 2>&1)"; \
		else \
			output="$$(cd infra/foundry-hosted && azd ai agent invoke order-resolution-hosted "$$message" --protocol responses --new-conversation --new-session --no-prompt 2>&1)"; \
		fi; \
		rc="$$?"; \
		set -e; \
		if [[ "$$rc" -eq 0 ]]; then \
			echo "$$output"; \
			exit 0; \
		fi; \
		if echo "$$output" | grep -Eqi 'context deadline exceeded|session_not_ready|HTTP (404|409|429|5[0-9]{2})'; then \
			echo "Transient smoke invoke failure ($$attempt/$$max_attempts); retrying in 15s..."; \
			echo "$$output"; \
			attempt="$$((attempt + 1))"; \
			sleep 15; \
			continue; \
		fi; \
		echo "$$output"; \
		exit "$$rc"; \
	done; \
	echo "Smoke invoke failed after $$max_attempts attempts."; \
	exit 1

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
