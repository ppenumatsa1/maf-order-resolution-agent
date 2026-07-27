# Engineering Operating Model

## Purpose

This is the canonical delivery contract for the repository.

- **You provide** architecture intent, business rules, and acceptance criteria.
- **Skills provide** current platform and SDK guidance.
- **Copilot provides** implementation, tests, infrastructure, and documentation.
- **Gates provide** correctness, recovery, telemetry, and evaluation evidence.

## Application-hosted policy

The FastAPI Container App is the only application host for the MAF workflow.
Foundry is limited to model inference and report-only evaluation of FastAPI
workflow captures. Do not introduce a Foundry application runtime or an
alternate orchestration path.

The deployment target is `rg-maf-ora-azure` in North Central US. East US is
not a target because of the current Azure PostgreSQL offer restriction.

## Delivery status

The current deployment plan is **Preparing**. It must not claim deployment or
validation until fresh evidence is recorded in `.azure/deployment-plan.md` and
`docs/design/issues-changes-fixes.md`.

## Definition of done

1. Acceptance criteria are met without changing stable HTTP, SSE, HITL, or
   persistence contracts unintentionally.
2. Applicable local tests and deterministic evaluation pass.
3. HITL checkpoint/resume and idempotency behavior remain correct.
4. Telemetry preserves correlated workflow and approval identifiers without
   recording content by default.
5. `make eval-foundry`, when applicable, is retained as report-only evidence.
6. Affected documentation is updated with the change.

## Gate matrix

| Change type | Required evidence |
| --- | --- |
| Application or contract change | `make test`, `make eval-backend`, `make test-e2e`, design review |
| HITL rule change | Applicable tests/eval cases and `hitl-approval-conditions.md` |
| Azure/IaC change | Local evidence, Bicep/AZD validation, `iac-review`, then `azure-validation` |
| Authorized deployment | App-hosted smoke, relevant parity checks, report-only evaluation, and telemetry validation |

## Baseline scenarios

- `ORD-1001`: low risk, no HITL expected.
- `ORD-1009`: high risk, HITL expected and resumable.
- Damaged item: HITL expected.
