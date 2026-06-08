from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from tools.mcp_tools import MCPKnowledgeTool
from workflows.checkpoint_store import CheckpointStore
from workflows.event_bus import EventBus
from workflows.sequential_resolution_workflow import (
    SequentialResolutionWorkflow,
    WorkflowContext,
)
from workflows.session_memory import SessionMemoryStore


@pytest.mark.asyncio
async def test_low_risk_flow_completes_without_hitl(tmp_path: Path) -> None:
    event_bus = EventBus()
    workflow = SequentialResolutionWorkflow(
        event_bus=event_bus,
        memory_store=SessionMemoryStore(tmp_path / "memory"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        mcp_tool=MCPKnowledgeTool(endpoint=None),
    )

    thread_id = str(uuid4())
    context = WorkflowContext(
        run_id=str(uuid4()),
        thread_id=thread_id,
        session_id=thread_id,
        customer_id="cust-test",
        user_message="Order ORD-1001 arrived a day late.",
    )
    await workflow.start(context)

    history = json.loads(event_bus.history_as_json(thread_id))
    assert any(event["type"] == "workflow.output" for event in history)
    assert not any(event["type"] == "hitl.request" for event in history)


@pytest.mark.asyncio
async def test_high_risk_flow_requests_hitl_then_resumes(tmp_path: Path) -> None:
    event_bus = EventBus()
    checkpoint_store = CheckpointStore(tmp_path / "checkpoints")
    workflow = SequentialResolutionWorkflow(
        event_bus=event_bus,
        memory_store=SessionMemoryStore(tmp_path / "memory"),
        checkpoint_store=checkpoint_store,
        mcp_tool=MCPKnowledgeTool(endpoint=None),
    )

    thread_id = str(uuid4())
    context = WorkflowContext(
        run_id=str(uuid4()),
        thread_id=thread_id,
        session_id=thread_id,
        customer_id="cust-test",
        user_message="Order ORD-1009 is delayed and I need compensation.",
    )
    await workflow.start(context)

    history = json.loads(event_bus.history_as_json(thread_id))
    checkpoint_event = next(
        event for event in history if event["type"] == "checkpoint.created"
    )
    checkpoint_id = checkpoint_event["payload"]["checkpoint_id"]

    await workflow.handle_hitl_response(
        checkpoint_id=checkpoint_id,
        decision="approve",
        reviewer="test-reviewer",
        comments="looks good",
    )

    resumed_history = json.loads(event_bus.history_as_json(thread_id))
    assert any(event["type"] == "hitl.response" for event in resumed_history)
    assert any(event["type"] == "workflow.output" for event in resumed_history)
