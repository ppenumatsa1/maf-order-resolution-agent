# Delivery Evidence

## Current status

**Deployed and validated.** The application is deployed to
`rg-maf-ora-azure` in North Central US. Smoke, hosted Playwright, report-only
evaluation, and Application Insights HITL correlation passed; the current
evidence is recorded in `.azure/deployment-plan.md`.

## Validation record

Keep the following evidence current for the deployed environment:

- `make test`
- `make eval-backend`
- `make test-e2e`
- `make docker-test`
- `./scripts/skills/design-review-skill.sh`
- Bicep/AZD, IaC, and Azure readiness validation

Do not retain historical deployment ledgers or references to retired hosting
paths in this document.
