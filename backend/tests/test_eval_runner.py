from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.infrastructure.events import EventBus
from app.infrastructure.mcp import MCPKnowledgeTool
from app.infrastructure.persistence import CheckpointStore
from app.infrastructure.persistence.session_memory import SessionMemoryStore
from app.maf.workflows.order_resolution import OrderResolutionWorkflow
from evals.eval_runner import EvalCase, _load_cases, _run_case


@pytest.mark.asyncio
async def test_run_case_handles_reject_flow(tmp_path: Path) -> None:
    workflow = OrderResolutionWorkflow(
        event_bus=EventBus(),
        memory_store=SessionMemoryStore(tmp_path / "memory"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        mcp_tool=MCPKnowledgeTool(endpoint=None),
    )
    case = EvalCase(
        id="reject-case",
        input="Order ORD-1009 arrived broken and needs replacement.",
        expect_hitl=True,
        expected_order_id="ord-1009",
        expected_issue_type="damaged_item",
        expected_policy="replacement_or_full_refund_with_photo_proof",
        expected_action="offer_replacement_or_full_refund",
        expected_amount=185.0,
        hitl_decision="reject",
        expected_terminal_status="escalated",
    )
    capture = await _run_case(case=case, workflow=workflow, event_bus=workflow.event_bus)
    assert capture["actual_hitl"] is True
    assert capture["last_output"]["status"] == "escalated"


@pytest.mark.asyncio
async def test_run_case_enforces_duplicate_hitl_idempotency(tmp_path: Path) -> None:
    workflow = OrderResolutionWorkflow(
        event_bus=EventBus(),
        memory_store=SessionMemoryStore(tmp_path / "memory"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        mcp_tool=MCPKnowledgeTool(endpoint=None),
    )
    case = EvalCase(
        id="duplicate-case",
        input="Order ORD-1009 is delayed and I need compensation.",
        expect_hitl=True,
        expected_order_id="ord-1009",
        expected_issue_type="late_delivery",
        expected_policy="refund_allowed_if_delay_exceeds_3_days",
        expected_action="issue_partial_refund",
        expected_amount=185.0,
        hitl_decision="approve",
        assert_duplicate_hitl_response=True,
        expected_terminal_status="completed",
    )
    capture = await _run_case(case=case, workflow=workflow, event_bus=workflow.event_bus)
    assert capture["actual_hitl"] is True
    assert capture["last_output"]["status"] == "completed"


def test_load_cases_rejects_invalid_hitl_decision(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "bad-case",
                        "input": "Order ORD-1001 is delayed.",
                        "expect_hitl": True,
                        "hitl_decision": "maybe",
                    }
                )
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _load_cases(dataset)
