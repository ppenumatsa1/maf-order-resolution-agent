# Scripts

- `foundry/deploy_public_dev.sh`: authenticated local release sequence.
- `foundry/hosted_e2e.sh`: Responses low-risk, approval, rejection, and
  duplicate-response regression.
- `foundry/verify_telemetry.sh`: bounded Application Insights telemetry check.
- `foundry/check_public_postgres_readiness.sh`: public PostgreSQL readiness.
- `playwright/`: local FastAPI/SSE/UI browser regression suite.
- `skills/`: operating-model enforcement and deterministic review gates.

GitHub Actions runs only credential-free CI. Use `make foundry-release` from an
authenticated local shell for Azure deployment and hosted validation.
