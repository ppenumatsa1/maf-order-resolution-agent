# Engineering Operating Model

## Purpose

This is the canonical delivery contract. Architecture intent and business rules
come from the team; skills provide current platform guidance; implementation
includes code, IaC, tests, and documentation; gates provide evidence.

## Runtime policy

This branch has two supported execution surfaces:

1. **Local full stack:** React, FastAPI, SSE, and PostgreSQL run through Docker
   or Make targets. This is the authoritative UI/API/event-contract surface.
2. **Public Foundry hosted agent:** `backend/foundry/main.py` exposes the same
   MAF service through the Responses protocol. It is intentionally not an HTTP
   replacement for the local FastAPI/SSE UI.

The public hosted target is `rg-maf-ora-foundry-public-dev2`, using project
`order-resolution-public-managed-dev` and Microsoft-managed Foundry agent state.
PostgreSQL remains the application-owned durable workflow/checkpoint store. No
customer-managed Foundry state service, app-hosted Azure runtime, or GitHub
deployment workflow is part of this branch.

## Non-negotiable contracts

- One MAF business workflow; deterministic triage is allowed only when Foundry
  model configuration is absent and never replaces orchestration.
- Stable local API/SSE event types remain `workflow.stage`, `tool.call`,
  `checkpoint.created`, `hitl.request`, `hitl.response`, and `workflow.output`.
- HITL rules remain deterministic and resumable. Approval completes; rejection
  escalates; duplicate responses are idempotent.
- Infrastructure permissions are declarative Bicep role assignments.
- Foundry hosting remains Responses-native through `backend/agent.yaml` and
  `backend/foundry/main.py`.

## Delivery and validation

| Change | Required local gates | Required public hosted gates |
| --- | --- | --- |
| Application behavior | `make test`, `make eval-backend`, `make test-e2e` | None unless hosted behavior changes |
| HITL or persistence | Local gates plus targeted resume/idempotency coverage | ORD-1001, ORD-1009, approval, rejection, duplicate-response E2E |
| Foundry runtime, IaC, release script | Local gates plus Bicep/script validation | Azure validation, `azd up`, smoke, hosted E2E, Foundry eval, telemetry |
| Documentation | Link and command accuracy checks | Update execution evidence when operations change |

GitHub Actions is credential-free CI only. It runs repository checks on
`ubuntu-latest` and never provisions or deploys Azure. The authenticated local
release command is:

```bash
AZURE_SUBSCRIPTION_ID="<subscription>" \
RUNTIME_DATABASE_URL="postgresql://...?...sslmode=require" \
POSTGRES_ADMIN_PASSWORD="<password>" \
make foundry-release
```

It runs local gates, `azd up --no-prompt`, combined hosted smoke/E2E, enforced Foundry
evaluation, and Application Insights verification.

## Evidence handoff

For every deployment-impacting change, record in
`docs/design/issues-changes-fixes.md`:

- commit and changed surfaces;
- local gate results;
- `azd up` result and hosted version/conversation IDs;
- Foundry evaluation ID/run/result counts;
- App Insights trace/dependency/exception evidence;
- known deferrals.

## Baseline scenarios

- `ORD-1001`: low risk, completes without HITL.
- `ORD-1009`: high amount (`185.0`), pauses for HITL and completes after approval.
- damaged item: pauses for HITL and escalates after rejection.
