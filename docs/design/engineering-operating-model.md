# Engineering Operating Model

## Purpose

This is the canonical delivery contract for this repository.

It formalizes the split:

- **You provide** architecture intent, business rules, and acceptance criteria.
- **Skills provide** current Microsoft platform and SDK guidance.
- **Copilot provides** implementation, tests, and infra/doc updates.
- **Gates provide** release evidence for correctness, recovery, telemetry, and Foundry parity.

This model is Pareto-first: start with the minimum enforceable contract and expand gates only when risk increases.

## Current lane policy

Hosted validation and deployment are private-lane-first in the current operating posture:

- **Default hosted lane:** private Foundry (`foundry-private-env` / private runner path).
- No additional hosted lane is part of the required gate path unless explicitly re-enabled by a documented decision update.

## Inputs and authority

### 1) Product and architecture inputs (user/team authority)

Required inputs before implementation:

- Architecture boundaries and explicit non-goals
- Business-rule truth conditions (including HITL triggers)
- Acceptance criteria in observable terms (events, outputs, state)
- Deployment lane scope (local runtime and private Foundry hosted lane)

### 2) Skill authority (implementation constraints)

Skills define current best-practice patterns for Microsoft services/SDKs and deployment guidance.

Skills do **not** override business rules or accepted contracts on their own. If skill guidance conflicts with accepted behavior/contracts, capture the delta as a documented decision and apply the smallest approved change.

### 3) Copilot delivery responsibilities

For each approved change, Copilot must deliver:

- Smallest complete code/IaC/script update that satisfies acceptance criteria
- Matching tests and contract-safe updates (API, SSE, HITL, persistence)
- Required documentation sync for changed behavior or operations
- Evidence artifacts from required gates

## Source-of-truth hierarchy

When guidance conflicts, resolve in this order:

1. `docs/design/engineering-operating-model.md` (this contract)
2. Architecture and behavior docs (`architecture.md`, `userflow.md`, `hitl-approval-conditions.md`, `prd.md`)
3. Repository instructions (`.github/copilot-instructions.md`, `agents.md`)
4. Skill guidance (stack/repository skills)
5. Inline comments/examples

## Definition of Done (minimum)

A change is done only when all applicable items are true:

1. Acceptance criteria are met without breaking stable contracts.
2. Required tests/gates pass for the change type.
3. Recovery behavior remains correct for stateful/HITL flows.
4. Telemetry remains correlated and free of new unhandled workflow exceptions.
5. Evaluation evidence is present: deterministic eval is green; Foundry evaluator run is published for hosted/runtime-impacting changes.
6. Required docs are updated in the same change set.
7. Evidence is recorded in `docs/design/issues-changes-fixes.md` when deploy/runtime behavior is involved.

## Change-to-gate matrix (Phase 1)

| Change type | Required local gates | Required hosted gates |
| --- | --- | --- |
| App-only behavior (no hosting/IaC change) | `make test`, `make eval-backend`, `make test-e2e`, `./scripts/skills/design-review-skill.sh` | None |
| HITL/business-rule change | local gates + targeted HITL rule assertions | Hosted smoke for `ORD-1001`, `ORD-1009` (+ approve/reject when applicable) |
| MAF/Foundry runtime change | local gates + focused hosted-entry tests + `make eval-backend` | Private Foundry deploy + smoke + E2E + telemetry verification + report-only `make eval-foundry` artifact |
| IaC/network/identity/deploy workflow change | local gates as applicable + IaC review | `azure-validation` -> `azure-deployment` -> `azure-telemetry-validation` |
| Persistence/checkpoint/idempotency change | local gates + restart/resume/idempotency assertions | Hosted smoke for resume and duplicate HITL response behavior |

## Operationalization (automated)

The CI workflow (`.github/workflows/ci.yml`) enforces this model in two lightweight stages:

1. **Routing** via `scripts/skills/deployment-mode-router.sh` to select `validation_mode` (`quick` or `full`) from changed surfaces.
2. **Guardrail enforcement** via `scripts/skills/operating-model-enforcement.sh`:
   - HITL decision-surface changes require `docs/design/hitl-approval-conditions.md` updates plus workflow-test or hosted-eval updates.
   - Hosted runtime/deploy surface changes require an update to `docs/design/issues-changes-fixes.md`.

## Evidence handoff template

For each release-impacting change, capture:

- Commit SHA and changed surfaces
- Gate results (pass/fail + command or run ID)
- Hosted version and conversation/thread identifiers
- Foundry trace evidence (version-scoped)
- App Insights correlation evidence (`workflow_run_id`, `thread_id`, exception status)
- Deferred items (explicitly marked deferred, not implied complete)

## Current baseline scenarios

- `ORD-1001`: low-risk path, no HITL expected.
- `ORD-1009`: high-risk path, HITL expected and resumable.
- Damaged item: HITL expected.
