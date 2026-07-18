---
name: release-readiness
description: Orchestrate focused repository skills for PR or release readiness across backend, docs, IaC, local validation, Azure validation, deployment, telemetry validation, and final design review.
---

# Release Readiness Skill

Use this skill when preparing a PR, release, or deployment handoff that may touch multiple repository surfaces.

## Principle

Compose focused skills instead of doing one broad review. Run only the skills relevant to the files changed, then run `design-review` as the final deterministic local gate.

## Skill routing

1. Backend/API/MAF changes -> run `backend-boundary-review`.
2. Documentation-impacting changes -> run `docs-sync`.
3. Local behavior changes -> run `local-validation`.
4. Azure/Foundry IaC, Docker, AZD, workflows, or smoke script changes -> run `iac-review`.
5. Azure readiness or deployed endpoint checks -> run `azure-validation`.
6. Already validated Azure deployment execution -> run `azure-deployment`.
7. Hosted App Insights proof after deployment -> run `azure-telemetry-validation`.
8. Workflow/runtime/HITL quality evidence -> run `foundry-agent-evaluation`.
9. Final local gate -> run `design-review`.

## Recommended sequence

1. Inspect changed files and classify affected surfaces.
2. Route validation/deployment mode with:

```bash
scripts/skills/deployment-mode-router.sh
```

   - `validation_mode=quick` -> run `quick-validation`
   - `validation_mode=full` -> run `local-validation`
   - `deploy_mode=app_only` -> use `azd deploy`
   - `deploy_mode=full` -> use `azd provision && azd deploy`
3. Run independent focused reviews in parallel when safe.
4. Apply only material fixes from focused reviews.
5. Run `docs-sync` after code/IaC behavior is settled.
6. Run quick or full local validation based on routing output.
7. Run `azure-validation` when Azure artifacts or live endpoints are involved.
8. Run `azure-deployment` only when the plan is validated and the user wants deployment.
9. Run `azure-telemetry-validation` after hosted deployment when App Insights telemetry is in scope.
10. Run `design-review` last to confirm the deterministic local gate.

For frontend or hosted endpoint readiness, require Playwright evidence in both local and hosted modes where applicable. Hosted proof must use `PLAYWRIGHT_BASE_URL=<frontend-url> make test-e2e` and must fail if Workflow History shows `Unexpected token`, `not valid JSON`, or `<!doctype`, which means the frontend received HTML instead of API JSON.

## Guardrails

- Keep changes surgical and simplicity-first.
- Do not use this skill as permission for broad refactors.
- Do not deploy from this skill directly; invoke `azure-deployment` for live deployment execution.
- Do not remove compatibility shims as part of release readiness unless shim removal is the explicit task.
- Report any skipped skill and why it was not applicable.

## Output

Report:

- skills run
- material findings fixed
- commands run
- blockers
- final readiness status
