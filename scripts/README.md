# Scripts

Scripts support local validation and the planned Azure app-hosted package.

## Key paths

- `playwright/`: browser workflow scenarios.
- `parity/`: local and Azure endpoint parity runner.
- `rubric/`: end-to-end quality rubric.
- `skills/design-review-skill.sh`: deterministic review gate.
- `skills/deployment-mode-router.sh`: validation/deployment routing.
- `azure/grant-postgres-identity.sh`: AZD post-provision PostgreSQL Entra grant.

## Local browser test

```bash
cd scripts/playwright
npm install
npx playwright install
PLAYWRIGHT_BASE_URL=http://localhost:5173 npm run test:e2e
```

## Endpoint parity

```bash
PARITY_LOCAL_API_URL=http://localhost:8000
PARITY_LOCAL_WEB_URL=http://localhost:5173
PARITY_AZURE_API_URL=https://<backend-host>
PARITY_AZURE_WEB_URL=https://<frontend-host>
make parity-all
```

The Azure variables are for authorized post-deployment validation only; this
branch currently makes no deployment claim.
