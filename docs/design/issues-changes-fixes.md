# Issues, Changes, and Fixes

## Public Foundry delivery ledger

### Architecture

The public hosted target is `rg-maf-ora-foundry-public-dev2`, project
`order-resolution-public-managed-dev`, and agent `order-resolution-hosted`.
Foundry manages agent sessions, files, and vector-store capabilities. PostgreSQL
remains the application-owned store for MAF workflow runs, checkpoints,
approvals, idempotency records, and audit events.

### Current implementation

1. The hosted runtime remains Responses-native through `backend/agent.yaml` and
   `backend/foundry/main.py`.
2. The Responses host uses Foundry's managed response store directly; no runtime
   profile switch or customer-owned Foundry state service is configured.
3. Public Bicep creates the Foundry project and its required identity/RBAC,
   references ACR and observability resources, preserves the existing
   PostgreSQL server, and provisions dedicated Blob storage and model capacity
   only for Foundry evaluation artifacts and judge calls.
4. Local authenticated release automation runs local validation, `azd up`,
   combined hosted smoke/E2E, enforced Foundry evaluation, and Application
   Insights verification.

### Verified evidence

1. Bicep build, ARM validation, and `azd provision --preview` passed. The
   preview creates the managed Foundry project without changing PostgreSQL.
2. Local backend tests, deterministic evaluation, local Playwright, Docker
   Playwright, and the deterministic design-review gate passed.
3. Managed project deployment succeeded. `order-resolution-hosted` version `1`
   is available through the Responses endpoint.
4. Hosted smoke and E2E passed for low-risk completion, high-risk approval,
   damaged-item rejection, follow-up continuity, and duplicate approval
   idempotency.
5. The local Docker full-stack browser suite passed all seven scenarios after
   recreating backend and mock-MCP containers. Fresh PostgreSQL audit rows cover
   completed and escalated runs, events, messages, checkpoints, approvals, and
   idempotency keys.
6. Public deployment version `3` succeeded on 2026-07-20 after pinning the
   hosted Oryx build to Python `3.13.9`; the unpinned build selected unavailable
   Python `3.13.11`.
7. Version `3` smoke and direct Responses E2E passed: low-risk completion and
   explanation continuity, high-risk approval/resume, damaged-item
   rejection/escalation, and a duplicate rejection that correctly returned no
   pending approval. The associated three conversations emitted 100 correlated
   App Insights trace/request/dependency rows with zero exceptions.
8. Version `5` deployed on 2026-07-20 with OpenTelemetry structured message
   parts (`parts[].content`) on the hosted invocation span. This is required
   for Foundry to materialize non-empty conversation messages during trace
   evaluation. Hosted smoke and the complete low-risk, approval/resume, and
   rejection/idempotency E2E suite passed.
9. The completed trace-evaluation run
   `eval_ed7f66fa5a4e40d1add7a5f89e9375a7` /
   `evalrun_bee66b5a37d4456aa7d577017e7eeadb` evaluated the version `5` E2E
   conversations with zero errored rows. It produced two passing and one
   failing conversation-level aggregate: the generic task-completion and
   coherence evaluators mark the intentional reviewer-rejection path as a
   customer-request failure. This is retained as a quality signal; it is not
   an execution failure and does not relax the enforced zero-error gate.
10. Application Insights verification for the same three conversations passed
   with 119 correlated rows and no exceptions.
11. Version `6` reduces the steady-state hosted release E2E evidence to two
   essential conversations: low-risk completion without HITL and high-risk
   approval/resume with HITL. Damaged-item rejection and duplicate-decision
   behavior remain covered by the local backend and Playwright suites; they
   are not repeated in the hosted release timing path. The first low-risk turn
   is also the release smoke assertion, removing the redundant standalone
   smoke invocation.
12. The two-conversation release path completed hosted E2E in 73 seconds on
   2026-07-20. Trace evaluation
   `eval_34872279fc4a442187a1a73110dc90f8` /
   `evalrun_035d442132a94e318d33ff989a7b3fbe` passed both conversations with
   zero errors, and Application Insights found 38 correlated rows without
   exceptions.
13. A version `7` steady-state release measurement completed in 4 minutes
   26 seconds: no-drift provision (46 seconds), deploy (96 seconds), combined
   smoke/E2E (74 seconds), trace evaluation (33 seconds), and telemetry
   correlation (17 seconds). Evaluation
   `eval_be3b5c4f61bf494c99847d0d53fc292c` /
   `evalrun_e159baea2efa48bdbb89db38aacf0d55` had zero errored rows; App
   Insights found 77 correlated rows for the two hosted conversations without
   exceptions.

### Foundry evaluation artifact store remediation

Both dataset and trace evaluation attempts reached Foundry's
`temporaryDataReference` asset-store stage and failed before a run was created.
The public managed project does not expose a Microsoft-managed storage
connection that can be granted RBAC. The remediation provisions a dedicated
public Standard LRS Blob account solely for Foundry evaluation artifacts,
creates an AAD account connection that Foundry materializes at project scope,
and grants the Foundry account and project managed identities `Storage Blob
Data Owner`, as required by Foundry evaluation guidance. The account is not
used by the workflow runtime, session store, vector store, or PostgreSQL audit
path.
The release gate remains enforced; do not relax `FOUNDRY_EVAL_MAX_ERRORED=0`.

### Evaluator capacity remediation

The original `gpt-4o-mini` deployment had 1K TPM and was shared by the hosted
workflow and evaluator. Although trace extraction succeeded, all evaluator
calls received `429 rate_limit_exceeded`. Bicep now provisions the dedicated
`gpt-4o-mini-evaluation` Global Standard deployment at 10K TPM and exports
`FOUNDRY_EVAL_MODEL`; the release script passes that output explicitly to
`make eval-foundry`. The evaluator timeout is 30 minutes to accommodate
Foundry's asynchronous scheduling while still treating failed, cancelled, and
errored runs as release failures.
