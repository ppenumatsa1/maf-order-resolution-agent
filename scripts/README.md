# Scripts

## Contents

- `rubric/e2e-rubric.md`: evaluation rubric for end-to-end workflow quality.
- `playwright/`: browser automation suite for key demo scenarios.
- `mcp/mock_mcp_server.py`: authenticated mock MCP endpoint for POC.
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
