# HITL Approval Trigger Conditions

This document defines the exact conditions that trigger human approval (`hitl.request`) in both workflow implementations, with test-ready examples.

## Scope

- Deterministic workflow: `backend/workflows/sequential_resolution_workflow.py`
- MAF SDK workflow: `backend/workflows/maf_sdk_workflow.py`

## Rule Summary

HITL is triggered if any of these are true:

1. Amount/risk is `>= 100`.
2. The issue type is `damaged_item`.
3. Policy contains `manual_review`.

If none of the above are true, the workflow completes directly without human approval.

## Deterministic Workflow Rules

Source behavior:

- `requires_hitl = policy["amount"] >= 100 or "manual_review" in policy["policy"]`
- If `issue_type == "damaged_item"`, `requires_hitl = True`

How values are derived:

- Amount comes from order status:
  - Order IDs ending with `9` -> amount `185.0`
  - Other order IDs -> amount `79.0`
- Issue classification:
  - Message contains `damage` or `broken` -> `damaged_item`
  - Message contains `wrong` -> `wrong_item`
  - Else -> `late_delivery`
- Policy strings:
  - `late_delivery` -> `refund_allowed_if_delay_exceeds_3_days`
  - `damaged_item` -> `replacement_or_full_refund_with_photo_proof`
  - `wrong_item` -> `free_replacement_and_return_label`
  - Unknown type fallback -> `manual_review_required`

## MAF SDK Workflow Rules

Source behavior:

- `requires_hitl = order.total_amount >= 100 or "manual_review" in policy or issue_type == "damaged_item"`

How values are derived:

- Issue classification is narrower:
  - Message contains `damaged` -> `damaged_item`
  - Else -> `late_delivery`
- Order ID mapping in this path:
  - Message containing `1009` -> `ord-1009` (amount `185.0`)
  - Else -> `ord-1001` (amount `79.0`)

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

4. Wrong item with low amount (deterministic workflow)

- Input: `Order ORD-1001 has the wrong item.`
- Expected: no `hitl.request`.
- Why: issue type `wrong_item`, amount `79.0`, policy string has no `manual_review`.

5. Wrong item with high amount (deterministic workflow)

- Input: `Order ORD-1009 has the wrong item.`
- Expected: `hitl.request` emitted.
- Why: amount `185.0`.

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

For non-HITL scenarios:

- No `hitl.request` event
- Final `workflow.output.status=completed`

## Existing Coverage

- `backend/tests/test_workflow.py` includes:
  - low-risk path without HITL
  - high-risk path with HITL and resume
- `backend/evals/cases.jsonl` includes mixed HITL expected outcomes.
