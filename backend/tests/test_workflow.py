from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from app.infrastructure.events import EventBus
from app.infrastructure.mcp import MCPKnowledgeTool
from app.infrastructure.persistence import CheckpointStore
from app.infrastructure.persistence.session_memory import SessionMemoryStore
from app.maf.clients import FoundryModelsConfig
from app.maf.workflows import order_resolution as workflow_module
from app.maf.workflows.order_resolution import OrderResolutionWorkflow
from app.modules.order_resolution.models import WorkflowContext


def _event_types(history: list[dict[str, object]]) -> list[str]:
    return [str(event["type"]) for event in history]


def _event_index(history: list[dict[str, object]], event_type: str) -> int:
    return next(i for i, event in enumerate(history) if event["type"] == event_type)


@pytest.fixture(autouse=True)
def clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MAF_PROVIDER",
        "MAF_MODEL",
        "FOUNDRY_PROJECTS_ENDPOINT",
        "FOUNDRY_PROJECT_ENDPOINT",
        "FOUNDRY_MODEL_DEPLOYMENT_NAME",
        "FOUNDRY_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_low_risk_flow_completes_without_hitl(tmp_path: Path) -> None:
    event_bus = EventBus()
    workflow = OrderResolutionWorkflow(
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
    event_types = _event_types(history)
    assert "workflow.output" in event_types
    assert "hitl.request" not in event_types

    stage_sequence = [
        (event["payload"]["agent"], event["payload"]["status"])
        for event in history
        if event["type"] == "workflow.stage"
    ]
    assert stage_sequence == [
        ("triage", "started"),
        ("triage", "completed"),
        ("policy_retrieval", "started"),
        ("policy_retrieval", "completed"),
        ("resolution", "completed"),
    ]
    triage_started = next(
        event
        for event in history
        if event["type"] == "workflow.stage"
        and event["payload"]["agent"] == "triage"
        and event["payload"]["status"] == "started"
    )
    assert triage_started["payload"]["triage_mode"] == {
        "provider": "deterministic",
        "mode": "local_fallback",
    }

    tool_event = next(event for event in history if event["type"] == "tool.call")
    assert isinstance(tool_event["payload"].get("policy_evidence_ids"), list)
    policy_retrieval = tool_event["payload"].get("policy_retrieval")
    assert isinstance(policy_retrieval, dict)
    assert isinstance(policy_retrieval.get("query_id"), str)
    assert tool_event["payload"].get("local_tool") == "fetch_order_status/fetch_policy"
    assert tool_event["payload"].get("mcp_tool") == "search"
    mcp_result = tool_event["payload"].get("mcp_result")
    assert isinstance(mcp_result, dict)
    assert mcp_result.get("source") in {"mcp-fallback", "mcp-remote"}

    output_event = next(event for event in history if event["type"] == "workflow.output")
    output_payload = output_event["payload"]
    assert output_payload.get("status") == "completed"
    assert isinstance(output_payload.get("submission_id"), str)
    assert "ord-" in str(output_payload.get("message", "")).lower()


@pytest.mark.asyncio
async def test_high_risk_flow_requests_hitl_then_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_context = {
        "trace_id": "1" * 32,
        "span_id": "2" * 16,
    }
    monkeypatch.setattr(workflow_module, "current_trace_context", lambda: trace_context)
    event_bus = EventBus()
    checkpoint_store = CheckpointStore(tmp_path / "checkpoints")
    workflow = OrderResolutionWorkflow(
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
    event_types = _event_types(history)
    assert "checkpoint.created" in event_types
    assert "hitl.request" in event_types
    assert "workflow.output" not in event_types

    checkpoint_event = next(event for event in history if event["type"] == "checkpoint.created")
    checkpoint_id = checkpoint_event["payload"]["checkpoint_id"]
    checkpoint_record = checkpoint_store.get(checkpoint_id)
    assert checkpoint_record is not None
    assert checkpoint_record["thread_id"] == thread_id
    assert checkpoint_record["status"] == "pending_hitl"
    checkpoint_state = checkpoint_record["state"]
    assert checkpoint_state["run_id"] == context.run_id
    assert checkpoint_state["session_id"] == context.session_id
    assert checkpoint_state["customer_id"] == context.customer_id
    assert checkpoint_state["order_id"].startswith("ord-")
    assert isinstance(checkpoint_state["action"], str)
    assert isinstance(checkpoint_state["amount"], float)
    assert checkpoint_state["telemetry_trace_context"] == trace_context

    await workflow.handle_hitl_response(
        checkpoint_id=checkpoint_id,
        decision="approve",
        reviewer="test-reviewer",
        comments="looks good",
    )

    resumed_history = json.loads(event_bus.history_as_json(thread_id))
    assert any(event["type"] == "hitl.response" for event in resumed_history)
    assert any(event["type"] == "workflow.output" for event in resumed_history)
    assert _event_index(resumed_history, "hitl.response") < _event_index(
        resumed_history, "workflow.output"
    )
    output_event = next(event for event in resumed_history if event["type"] == "workflow.output")
    output_payload = output_event["payload"]
    assert output_payload.get("status") == "completed"
    assert isinstance(output_payload.get("submission_id"), str)
    assert checkpoint_state["order_id"] in str(output_payload.get("message", ""))


@pytest.mark.asyncio
async def test_broken_item_always_requests_hitl(tmp_path: Path) -> None:
    event_bus = EventBus()
    workflow = OrderResolutionWorkflow(
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
        user_message="Order ORD-1001 arrived broken.",
    )
    await workflow.start(context)

    history = json.loads(event_bus.history_as_json(thread_id))
    assert any(event["type"] == "hitl.request" for event in history)


@pytest.mark.asyncio
async def test_high_risk_rejection_emits_escalated_terminal_output(tmp_path: Path) -> None:
    event_bus = EventBus()
    checkpoint_store = CheckpointStore(tmp_path / "checkpoints")
    workflow = OrderResolutionWorkflow(
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
    checkpoint_event = next(event for event in history if event["type"] == "checkpoint.created")
    checkpoint_id = checkpoint_event["payload"]["checkpoint_id"]

    await workflow.handle_hitl_response(
        checkpoint_id=checkpoint_id,
        decision="reject",
        reviewer="test-reviewer",
        comments="policy threshold not met",
    )

    resumed_history = json.loads(event_bus.history_as_json(thread_id))
    output_event = next(event for event in resumed_history if event["type"] == "workflow.output")
    output_payload = output_event["payload"]
    assert output_payload == {
        "message": "Request rejected by reviewer. Escalating to human support specialist.",
        "status": "escalated",
    }
    checkpoint_record = checkpoint_store.get(checkpoint_id)
    assert checkpoint_record is not None
    assert checkpoint_record["status"] == "rejected"
    assert checkpoint_record["reviewer"] == "test-reviewer"


@pytest.mark.asyncio
async def test_retries_read_only_paths_before_succeeding(tmp_path: Path) -> None:
    event_bus = EventBus()
    workflow = OrderResolutionWorkflow(
        event_bus=event_bus,
        memory_store=SessionMemoryStore(tmp_path / "memory"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        mcp_tool=MCPKnowledgeTool(endpoint=None),
    )

    model_attempts = {"count": 0}
    mcp_attempts = {"count": 0}

    async def flaky_model(*_args: object, **_kwargs: object) -> str:
        model_attempts["count"] += 1
        if model_attempts["count"] < 2:
            raise RuntimeError("transient model error")
        return "triage_summary: ok"

    async def flaky_mcp(_query: str) -> dict[str, object]:
        mcp_attempts["count"] += 1
        if mcp_attempts["count"] < 2:
            raise RuntimeError("transient mcp error")
        return {"source": "mcp-remote", "result": {"ok": True}}

    workflow._run_maf_sequence = flaky_model  # type: ignore[method-assign]
    workflow.mcp_tool.search = flaky_mcp  # type: ignore[method-assign]
    workflow.retry_attempts = 3
    workflow.retry_delay_seconds = 0

    thread_id = str(uuid4())
    context = WorkflowContext(
        run_id=str(uuid4()),
        thread_id=thread_id,
        session_id=thread_id,
        customer_id="cust-test",
        user_message="Order ORD-1001 arrived a day late.",
    )
    await workflow.start(context)

    assert model_attempts["count"] == 2
    assert mcp_attempts["count"] == 2


@pytest.mark.asyncio
async def test_foundry_config_emits_foundry_triage_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "FOUNDRY_PROJECTS_ENDPOINT", "https://example.services.ai.azure.com/api/projects/p"
    )
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")
    created_agents: list[dict[str, object]] = []
    credential_closed = {"value": False}

    class DummyClient:
        def as_agent(self, **kwargs: object) -> str:
            created_agents.append(kwargs)
            return str(kwargs["name"])

    class DummyCredential:
        async def close(self) -> None:
            credential_closed["value"] = True

    class DummyEvent:
        type = "output"
        data = "triage_summary: order_id=ord-1001; issue_type=late_delivery"

    class DummyStream:
        def __init__(self) -> None:
            self._sent = False

        def __aiter__(self) -> DummyStream:
            return self

        async def __anext__(self) -> DummyEvent:
            if self._sent:
                raise StopAsyncIteration
            self._sent = True
            return DummyEvent()

        async def get_final_response(self) -> object:
            raise AssertionError("streamed output should be used")

    class DummyWorkflow:
        def run(self, *, message: str, stream: bool = False) -> DummyStream:
            assert stream is True
            assert "request:" in message
            return DummyStream()

    class DummySequentialBuilder:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["participants"] == ["TriageAgent", "PolicyAgent", "ResolutionAgent"]
            assert kwargs["intermediate_output_from"] == ["TriageAgent", "PolicyAgent"]

        def build(self) -> DummyWorkflow:
            return DummyWorkflow()

    config = FoundryModelsConfig(
        project_endpoint="https://example.services.ai.azure.com/api/projects/p",
        model="gpt-4.1-mini",
    )
    monkeypatch.setattr(
        workflow_module,
        "create_foundry_chat_client",
        lambda _config: (DummyClient(), DummyCredential(), config),
    )
    event_bus = EventBus()
    workflow = OrderResolutionWorkflow(
        event_bus=event_bus,
        memory_store=SessionMemoryStore(tmp_path / "memory"),
        checkpoint_store=CheckpointStore(tmp_path / "checkpoints"),
        mcp_tool=MCPKnowledgeTool(endpoint=None),
    )
    workflow._SequentialBuilder = DummySequentialBuilder

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
    triage_events = [
        event
        for event in history
        if event["type"] == "workflow.stage" and event["payload"]["agent"] == "triage"
    ]
    assert [event["payload"]["status"] for event in triage_events] == ["started", "completed"]
    assert all(
        event["payload"]["triage_mode"]
        == {
            "provider": "foundry",
            "mode": "foundry_models",
            "model": "gpt-4.1-mini",
        }
        for event in triage_events
    )
    assert credential_closed["value"] is True
    assert [agent["name"] for agent in created_agents] == [
        "TriageAgent",
        "PolicyAgent",
        "ResolutionAgent",
    ]
    assert all(agent["default_options"] == {"store": False} for agent in created_agents)


@pytest.mark.asyncio
async def test_submit_resolution_is_idempotent_for_duplicate_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_bus = EventBus()
    checkpoint_store = CheckpointStore(tmp_path / "checkpoints")
    workflow = OrderResolutionWorkflow(
        event_bus=event_bus,
        memory_store=SessionMemoryStore(tmp_path / "memory"),
        checkpoint_store=checkpoint_store,
        mcp_tool=MCPKnowledgeTool(endpoint=None),
    )

    submit_calls = {"count": 0}

    def fake_submit_resolution(*, action: str, order_id: str) -> str:
        submit_calls["count"] += 1
        return f"resolution_submitted::{action}::{order_id}"

    monkeypatch.setattr(workflow_module, "submit_resolution", fake_submit_resolution)

    thread_id = str(uuid4())
    run_id = str(uuid4())
    context = WorkflowContext(
        run_id=run_id,
        thread_id=thread_id,
        session_id=thread_id,
        customer_id="cust-test",
        user_message="Order ORD-1009 is delayed and I need compensation.",
    )
    await workflow.start(context)

    history = json.loads(event_bus.history_as_json(thread_id))
    checkpoint_event = next(event for event in history if event["type"] == "checkpoint.created")
    checkpoint_id = checkpoint_event["payload"]["checkpoint_id"]

    await workflow.handle_hitl_response(
        checkpoint_id=checkpoint_id,
        decision="approve",
        reviewer="test-reviewer",
        comments="looks good",
    )
    await workflow.handle_hitl_response(
        checkpoint_id=checkpoint_id,
        decision="approve",
        reviewer="test-reviewer",
        comments="repeated call",
    )

    assert submit_calls["count"] == 1

    resumed_history = json.loads(event_bus.history_as_json(thread_id))
    hitl_responses = [e for e in resumed_history if e["type"] == "hitl.response"]
    outputs = [e for e in resumed_history if e["type"] == "workflow.output"]
    assert len(hitl_responses) == 1
    assert len(outputs) == 1
