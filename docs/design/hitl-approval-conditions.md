# HITL Approval Trigger Conditions

This document defines the exact conditions that trigger human approval (`hitl.request`) in the MAF SDK workflow, with test-ready examples.

## Journey Context (Local MAF -> Azure app-hosted -> Foundry-hosted)

- Local MAF path is implemented and currently active (`WORKFLOW_MODE=maf_sdk`).
- Azure app-hosted and Foundry-hosted modes are scaffolded for future phases.
- Therefore, the trigger behavior below is the **current production contract** for this repository runtime.

## Scope

- MAF SDK workflow: `backend/app/maf/workflows/order_resolution.py` (`backend/workflows/maf_sdk_workflow.py` remains a compatibility wrapper)
- API-facing run/HITL requests now enter through `backend/app/modules/order_resolution/service.py`; this service delegates to the same MAF SDK workflow and does not change trigger behavior.

## Rule Summary

HITL is triggered if any of these are true:

1. Amount/risk is `>= 100`.
2. The issue type is `damaged_item`.
3. Policy contains `manual_review`.

If none of the above are true, the workflow completes directly without human approval.

Policy retrieval through local pgvector-compatible RAG is now performed before resolution, but it is non-blocking and does not alter the trigger rules above.

## MAF SDK Workflow Rules

Source behavior:

- `requires_hitl = order.total_amount >= 100 or "manual_review" in policy or issue_type == "damaged_item"`

How values are derived:

- Issue classification:
  - Message contains `damage` or `broken` -> `damaged_item`
  - Message contains `wrong` -> `wrong_item`
  - Else -> `late_delivery`
- Order ID mapping in this path:
  - Message containing `1009` -> `ord-1009` (amount `185.0`)
  - Else -> `ord-1001` (amount `79.0`)
- Policy lookup:
  - `late_delivery` -> `refund_allowed_if_delay_exceeds_3_days`
  - `damaged_item` -> `replacement_or_full_refund_with_photo_proof`
  - `wrong_item` -> `free_replacement_and_return_label`
  - Unknown issue types -> `manual_review_required` (this satisfies the `manual_review` trigger condition)

## Test Matrix (Easy to Reproduce)

1. High amount approval trigger

- Input: `Order ORD-1009 is delayed by 5 days. I need compensation.`
- Expected: `hitl.request` emitted.
- Why: amount is `185.0`.

2. Damaged item approval trigger

- Input: `Order ORD-1001 arrived damaged and broken.`
- Expected: `hitl.request` emitted.
- Why: issue type is `damaged_item`.

3. Low-risk no-approval path

- Input: `Order ORD-1001 arrived late by 1 day. What can you do?`
- Expected: no `hitl.request`; direct `workflow.output` with `status=completed`.
- Why: amount `79.0`, no `manual_review`, non-damaged issue.

4. Wrong item no-approval path (current classifier behavior)

- Input: `Order ORD-1001 has the wrong item in the box.`
- Expected: no `hitl.request`; direct `workflow.output` with `status=completed`.
- Why: issue type `wrong_item`, amount `79.0`, and policy does not include `manual_review`.

## What to Assert in Tests

For HITL-required scenarios:

- `checkpoint.created` event exists with `reason=approval_required`
- `hitl.request` event exists with:
  - `checkpoint_id`
  - `action`
  - `order_id`
  - `amount`
- After approval API call:
  - `hitl.response` exists
  - final `workflow.output.status=completed`
- After rejection API call:
  - final `workflow.output.status=escalated`
- Repeated approval/rejection submission for the same `checkpoint_id` remains idempotent:
  - only one `hitl.response`
  - only one terminal `workflow.output`

For non-HITL scenarios:

- No `hitl.request` event
- Final `workflow.output.status=completed`

## Existing Coverage

- `backend/tests/test_workflow.py` includes:
  - low-risk path without HITL
  - high-risk path with HITL and resume
- `backend/evals/cases.jsonl` includes mixed HITL expected outcomes.
