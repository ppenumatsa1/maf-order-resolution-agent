# Scripts

## Contents

- `rubric/e2e-rubric.md`: evaluation rubric for end-to-end workflow quality.
- `playwright/`: browser automation suite for key demo scenarios.
- `mcp/mock_mcp_server.py`: authenticated mock MCP endpoint for POC.
- `parity/`: multi-target parity runner for local/Azure/Foundry endpoint checks.
- `skills/design-review-skill.sh`: deterministic design-review validation entry point used by `/fleet` skill.
- `skills/deployment-mode-router.sh`: routes quick/full validation and app-only/full deployment based on changed files.

## Run Playwright locally

```bash
cd scripts/playwright
npm install
npx playwright install
PLAYWRIGHT_BASE_URL=http://localhost:5173 npm run test:e2e
```

Playwright writes artifacts under `scripts/playwright/.artifacts/` (test results + HTML report).

## Run endpoint parity checks

Set endpoint matrix environment variables (directly or via `PARITY_ENV_FILE`):

```bash
PARITY_LOCAL_API_URL=http://localhost:8000
PARITY_LOCAL_WEB_URL=http://localhost:5173
PARITY_AZURE_API_URL=https://<azure-backend-host>
PARITY_AZURE_WEB_URL=https://<azure-web-host>
PARITY_FOUNDRY_API_URL=https://<foundry-backend-host>
PARITY_FOUNDRY_WEB_URL=https://<foundry-web-host>
```

Run:

```bash
make parity-all
```

`make parity-all` is the single parity gate for this POC and always runs all three targets (`local`, `azure`, `foundry`) with the fast profile. Reports are written to `scripts/parity/reports/`.

Fast profile coverage:

- manual matrix baseline cases: `ORD-1001` and `ORD-1009`
- all event contract cases from `scripts/parity/contract.json`
- Playwright UI smoke subset:
  - `high-risk request triggers HITL and approve path completes`
  - `low-risk request completes without HITL`
  - `reject decision escalates workflow`

If you need a one-off exhaustive run, invoke the runner directly:

```bash
python3 scripts/parity/run_parity_matrix.py --targets local azure foundry --profile full
```

For `azure` and `foundry` targets, the parity runner now applies hosted-safe Playwright defaults automatically:

- `PLAYWRIGHT_EXPECT_TIMEOUT_MS=60000`
- `PLAYWRIGHT_TEST_TIMEOUT_MS=120000`
- `PLAYWRIGHT_CASE_DELAY_MS=15000`

You can still override these via environment variables when needed.

## Run with Docker Compose profile

```bash
docker compose --profile test up --build --abort-on-container-exit playwright
```

## Run mock MCP server locally

```bash
export MOCK_MCP_API_KEY=demo-api-key
export MOCK_MCP_BEARER_TOKEN=demo-bearer-token
make run-mock-mcp
```
