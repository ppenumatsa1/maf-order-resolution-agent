# Public Foundry Delivery Ledger

## Current architecture

The supported hosted path is:

```text
Browser
  -> external React/Nginx frontend Container App
  -> same-origin /api and SSE proxy
  -> internal FastAPI responses-wrapper Container App
  -> managed-identity Foundry Responses agent
  -> shared PostgreSQL workflow/checkpoint/approval/event state
```

The browser never receives a Foundry endpoint credential. The wrapper creates a
Foundry `conv_...` conversation before the first request, persists that thread
identifier, dispatches the initial Responses request without remote streaming,
and resumes HITL using checkpoint-keyed `function_call_output`. Browser live
updates come from persisted PostgreSQL projections through polling and stable
native SSE; the rich stream is additive.

## Current public target

- Resource group: `rg-maf-ora-foundry-public-dev2`
- Foundry project: `order-resolution-public-managed-dev2`
- Hosted agent: `order-resolution-hosted`
- Public frontend:
  `https://ora-public-dev2-frontend.greentree-dc9ce897.eastus2.azurecontainerapps.io/`
- Backend: internal-only Container App; it is not a browser endpoint.

## Verified release evidence

- Local backend tests, deterministic evaluation, local Playwright, Docker
  Playwright, and the deterministic review gate passed.
- Hosted browser Playwright passed all seven workflow scenarios, including
  low-risk completion, approval/resume, damaged-item rejection, workflow
  history, and native/rich event presentation.
- Direct Foundry Responses E2E passed for low-risk and HITL approval/resume.
- Enforced Foundry trace evaluation
  `eval_e41c203d70bd4a0782778954f7d73db4` /
  `evalrun_958cceeac33848b693928863e957e41b` completed with two passed, zero
  failed, and zero errored conversations.
- Application Insights correlation verified workflow and HITL spans for the
  hosted E2E conversations.

## Telemetry signal policy

The public project and both Container Apps export to the configured Application
Insights resource. FastAPI `/health`, `/api/health`, and chat SSE request spans
are intentionally excluded from request telemetry so Container Apps probes and
long-lived streams do not obscure workflow signal. Foundry `/readiness`,
invocation, model, workflow, checkpoint, and HITL spans remain observable.

Use a workflow dependency query rather than the portal's newest-first Search
list when investigating a conversation:

```kusto
AppDependencies
| where TimeGenerated > ago(6h)
| where Name startswith "workflow."
| extend thread_id = tostring(Properties["workflow.thread_id"])
| project TimeGenerated, Name, thread_id, OperationId
| order by TimeGenerated desc
```

Open an end-to-end transaction for a returned `OperationId` to inspect the
correlated Foundry, model, workflow, and HITL hierarchy.
