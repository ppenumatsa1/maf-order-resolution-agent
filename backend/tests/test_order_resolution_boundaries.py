from __future__ import annotations

import json
from typing import Any

import pytest
from app.api.v1.schemas.chat import ChatRunRequest
from app.api.v1.schemas.hitl import HitlResponseRequest
from app.infrastructure.events import EventBus
from app.maf.middleware import (
    WorkflowEventEnricher,
    WorkflowMiddlewareContext,
    execute_with_failure_event,
)
from app.modules.order_resolution import events as event_types
from app.modules.order_resolution.models import WorkflowContext, WorkflowEvent
from app.modules.order_resolution.projections import WorkflowRunEventProjector
from app.modules.order_resolution.rich_events import rich_events_for_workflow_event
from app.modules.order_resolution.service import OrderResolutionService


class FakeWorkflow:
    def __init__(self) -> None:
        self.started_context: WorkflowContext | None = None
        self.hitl_response: dict[str, Any] | None = None

    async def start(self, context: WorkflowContext) -> None:
        self.started_context = context

    async def handle_hitl_response(
        self,
        checkpoint_id: str,
        decision: str,
        reviewer: str,
        comments: str | None,
    ) -> str:
        self.hitl_response = {
            "checkpoint_id": checkpoint_id,
            "decision": decision,
            "reviewer": reviewer,
            "comments": comments,
        }
        return "thread-123"


class FakeWorkflowRunRepository:
    def __init__(self) -> None:
        self.created_runs: list[dict[str, Any]] = []
        self.events: list[WorkflowEvent] = []
        self.status_updates: list[tuple[str, str]] = []
        self.stage_updates: list[tuple[str, str | None]] = []
        self.latest_outputs: list[tuple[str, dict[str, Any]]] = []
        self.pending_approvals: list[tuple[str, dict[str, Any]]] = []
        self.resolved_approvals: list[dict[str, Any]] = []
        self.responses_dispatches: dict[str, dict[str, str]] = {}
        self.pending_approval_status = "pending"

    def create_workflow_run(
        self,
        thread_id: str,
        input_text: str,
        session_id: str | None = None,
        customer_id: str | None = None,
    ) -> None:
        self.created_runs.append(
            {
                "thread_id": thread_id,
                "input_text": input_text,
                "session_id": session_id,
                "customer_id": customer_id,
            }
        )

    def append_workflow_event(self, _thread_id: str, event: WorkflowEvent) -> None:
        self.events.append(event)

    def update_current_stage(self, thread_id: str, stage: str | None) -> None:
        self.stage_updates.append((thread_id, stage))

    def add_pending_approval(self, thread_id: str, approval: dict[str, Any]) -> None:
        self.pending_approvals.append((thread_id, approval))

    def update_workflow_status(self, thread_id: str, status: str) -> None:
        self.status_updates.append((thread_id, status))

    def resolve_approval(
        self,
        thread_id: str,
        checkpoint_id: str,
        decision: str,
        comment: str | None,
        reviewer: str | None,
    ) -> None:
        self.resolved_approvals.append(
            {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "decision": decision,
                "comment": comment,
                "reviewer": reviewer,
            }
        )

    def update_latest_output(self, thread_id: str, output: dict[str, Any]) -> None:
        self.latest_outputs.append((thread_id, output))

    def get_pending_approval_context(self, checkpoint_id: str) -> dict[str, str] | None:
        if checkpoint_id == "checkpoint-123":
            return {
                "thread_id": "thread-123",
                "status": self.pending_approval_status,
            }
        return None

    def create_or_get_responses_dispatch(
        self,
        *,
        idempotency_key: str,
        request_hash: str,
        run_id: str,
        thread_id: str,
    ) -> dict[str, str]:
        existing = self.responses_dispatches.get(idempotency_key)
        if existing is not None:
            if existing["request_hash"] != request_hash:
                raise ValueError("Idempotency key was already used with a different request.")
            return {**existing, "created": False}
        dispatch = {
            "request_hash": request_hash,
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "pending",
        }
        self.responses_dispatches[idempotency_key] = dispatch
        return {**dispatch, "created": True}

    def update_responses_dispatch_status(self, idempotency_key: str, status: str) -> None:
        self.responses_dispatches[idempotency_key]["status"] = status

    def update_responses_dispatch_thread(self, idempotency_key: str, thread_id: str) -> None:
        self.responses_dispatches[idempotency_key]["thread_id"] = thread_id


class FakeResponsesWorkflow:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.responses: list[dict[str, str]] = []
        self.response_thread_id: str | None = None
        self.start_error: Exception | None = None

    async def start_workflow(
        self,
        *,
        thread_id: str,
        message: str,
        create_conversation: bool = True,
    ) -> str:
        self.started.append(
            {
                "thread_id": thread_id,
                "message": message,
                "create_conversation": create_conversation,
            }
        )
        if self.start_error is not None:
            raise self.start_error
        return self.response_thread_id or thread_id

    async def respond_to_hitl(
        self,
        *,
        thread_id: str,
        checkpoint_id: str,
        decision: str,
    ) -> None:
        self.responses.append(
            {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "decision": decision,
            }
        )


@pytest.mark.asyncio
async def test_order_resolution_service_starts_workflow_through_facade() -> None:
    workflow = FakeWorkflow()
    repository = FakeWorkflowRunRepository()
    service = OrderResolutionService(
        workflow=workflow,
        workflow_run_repository=repository,
    )

    response = await service.start_chat_run(
        ChatRunRequest(
            message="Order ORD-1001 arrived late.",
            thread_id="thread-123",
            session_id="session-123",
            customer_id="cust-123",
        )
    )

    assert response.thread_id == "thread-123"
    assert workflow.started_context == WorkflowContext(
        run_id=response.run_id,
        thread_id="thread-123",
        session_id="session-123",
        customer_id="cust-123",
        user_message="Order ORD-1001 arrived late.",
    )
    assert repository.created_runs == [
        {
            "thread_id": "thread-123",
            "input_text": "Order ORD-1001 arrived late.",
            "session_id": "session-123",
            "customer_id": "cust-123",
        }
    ]


@pytest.mark.asyncio
async def test_order_resolution_service_handles_hitl_through_facade() -> None:
    workflow = FakeWorkflow()
    repository = FakeWorkflowRunRepository()
    service = OrderResolutionService(
        workflow=workflow,
        workflow_run_repository=repository,
    )

    response = await service.respond_hitl(
        HitlResponseRequest(
            checkpoint_id="checkpoint-123",
            decision="approve",
            reviewer="reviewer-123",
            comments="approved",
        )
    )

    assert response.thread_id == "thread-123"
    assert workflow.hitl_response == {
        "checkpoint_id": "checkpoint-123",
        "decision": "approve",
        "reviewer": "reviewer-123",
        "comments": "approved",
    }


@pytest.mark.asyncio
async def test_order_resolution_service_delegates_to_responses_without_second_workflow() -> None:
    workflow = FakeWorkflow()
    repository = FakeWorkflowRunRepository()
    responses = FakeResponsesWorkflow()
    service = OrderResolutionService(
        workflow=workflow,
        workflow_run_repository=repository,
        responses_client=responses,
    )

    response = await service.start_chat_run(
        ChatRunRequest(message="Order ORD-1001 arrived late.", thread_id="thread-123")
    )
    hitl_response = await service.respond_hitl(
        HitlResponseRequest(checkpoint_id="checkpoint-123", decision="approve")
    )

    assert response.thread_id == "thread-123"
    assert workflow.started_context is None
    assert repository.created_runs == []
    assert responses.started == [
        {
            "thread_id": "thread-123",
            "message": "Order ORD-1001 arrived late.",
            "create_conversation": False,
        }
    ]
    assert hitl_response.thread_id == "thread-123"
    assert responses.responses == [
        {
            "thread_id": "thread-123",
            "checkpoint_id": "checkpoint-123",
            "decision": "approve",
        }
    ]


@pytest.mark.asyncio
async def test_responses_wrapper_does_not_replay_an_ambiguous_dispatch() -> None:
    workflow = FakeWorkflow()
    repository = FakeWorkflowRunRepository()
    responses = FakeResponsesWorkflow()
    service = OrderResolutionService(
        workflow=workflow,
        workflow_run_repository=repository,
        responses_client=responses,
    )
    request = ChatRunRequest(
        message="Order ORD-1001 arrived late.",
        thread_id="thread-123",
        idempotency_key="request-123",
    )

    first_response = await service.start_chat_run(request)
    second_response = await service.start_chat_run(request)

    assert first_response == second_response
    assert len(responses.started) == 1
    assert repository.responses_dispatches["request-123"]["status"] == "submitted"


@pytest.mark.asyncio
async def test_responses_wrapper_reuses_an_auto_created_dispatch() -> None:
    workflow = FakeWorkflow()
    repository = FakeWorkflowRunRepository()
    responses = FakeResponsesWorkflow()
    responses.response_thread_id = "conv-123"
    service = OrderResolutionService(
        workflow=workflow,
        workflow_run_repository=repository,
        responses_client=responses,
    )
    request = ChatRunRequest(
        message="Order ORD-1001 arrived late.",
        idempotency_key="request-123",
    )

    first_response = await service.start_chat_run(request)
    second_response = await service.start_chat_run(request)

    assert first_response.thread_id == "conv-123"
    assert second_response == first_response
    assert len(responses.started) == 1
    assert responses.started[0]["create_conversation"] is True


@pytest.mark.asyncio
async def test_responses_wrapper_does_not_retry_an_uncertain_dispatch() -> None:
    workflow = FakeWorkflow()
    repository = FakeWorkflowRunRepository()
    responses = FakeResponsesWorkflow()
    responses.start_error = RuntimeError("connection dropped")
    service = OrderResolutionService(
        workflow=workflow,
        workflow_run_repository=repository,
        responses_client=responses,
    )
    request = ChatRunRequest(
        message="Order ORD-1001 arrived late.",
        idempotency_key="request-123",
    )

    with pytest.raises(RuntimeError, match="connection dropped"):
        await service.start_chat_run(request)
    retry = await service.start_chat_run(request)

    assert retry.status == "accepted"
    assert len(responses.started) == 1
    assert repository.responses_dispatches["request-123"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_responses_wrapper_does_not_repeat_resolved_hitl_response() -> None:
    workflow = FakeWorkflow()
    repository = FakeWorkflowRunRepository()
    responses = FakeResponsesWorkflow()
    service = OrderResolutionService(
        workflow=workflow,
        workflow_run_repository=repository,
        responses_client=responses,
    )

    await service.respond_hitl(
        HitlResponseRequest(checkpoint_id="checkpoint-123", decision="approve")
    )
    repository.pending_approval_status = "resolved"
    replay = await service.respond_hitl(
        HitlResponseRequest(checkpoint_id="checkpoint-123", decision="approve")
    )

    assert replay.accepted is True
    assert len(responses.responses) == 1


def test_workflow_run_event_projector_syncs_hitl_and_output_events() -> None:
    repository = FakeWorkflowRunRepository()
    projector = WorkflowRunEventProjector(repository)

    projector.sync_event_to_run(
        WorkflowEvent(
            type="hitl.request",
            thread_id="thread-123",
            payload={"checkpoint_id": "11111111-1111-1111-1111-111111111111"},
        )
    )
    projector.sync_event_to_run(
        WorkflowEvent(
            type="hitl.response",
            thread_id="thread-123",
            payload={
                "checkpoint_id": "11111111-1111-1111-1111-111111111111",
                "decision": "approve",
                "reviewer": "reviewer-123",
                "comments": "approved",
            },
        )
    )
    projector.sync_event_to_run(
        WorkflowEvent(
            type="workflow.output",
            thread_id="thread-123",
            payload={"status": "completed", "message": "done"},
        )
    )

    assert repository.pending_approvals == [
        (
            "thread-123",
            {"checkpoint_id": "11111111-1111-1111-1111-111111111111"},
        )
    ]
    assert repository.resolved_approvals == [
        {
            "thread_id": "thread-123",
            "checkpoint_id": "11111111-1111-1111-1111-111111111111",
            "decision": "approve",
            "comment": "approved",
            "reviewer": "reviewer-123",
        }
    ]
    assert repository.latest_outputs == [("thread-123", {"status": "completed", "message": "done"})]
    assert repository.status_updates == [
        ("thread-123", "waiting_approval"),
        ("thread-123", "running"),
        ("thread-123", "completed"),
    ]


def test_workflow_event_enricher_adds_correlation_without_overwriting_payload() -> None:
    context = WorkflowContext(
        run_id="run-123",
        thread_id="thread-123",
        session_id="session-123",
        customer_id="cust-123",
        user_message="Order ORD-1001 arrived late.",
    )
    payload = {"agent": "triage", "workflow_run_id": "existing-run"}

    enriched = WorkflowEventEnricher().enrich(context, payload)

    assert enriched == {
        "agent": "triage",
        "workflow_run_id": "existing-run",
        "session_id": "session-123",
    }
    assert payload == {"agent": "triage", "workflow_run_id": "existing-run"}


@pytest.mark.asyncio
async def test_workflow_middleware_emits_failure_before_reraising() -> None:
    context = WorkflowContext(
        run_id="run-123",
        thread_id="thread-123",
        session_id="session-123",
        customer_id="cust-123",
        user_message="Order ORD-1001 arrived late.",
    )
    failures: list[tuple[WorkflowContext, Exception]] = []

    async def operation() -> None:
        raise RuntimeError("model unavailable")

    async def emit_failure(run_context: WorkflowContext, exc: Exception) -> None:
        failures.append((run_context, exc))

    with pytest.raises(RuntimeError, match="model unavailable"):
        await execute_with_failure_event(
            WorkflowMiddlewareContext(workflow="order_resolution", run=context),
            operation,
            emit_failure,
        )

    assert failures[0][0] == context
    assert str(failures[0][1]) == "model unavailable"


def test_rich_events_project_native_stage_tool_hitl_and_output_events() -> None:
    stage_events = rich_events_for_workflow_event(
        WorkflowEvent(
            type=event_types.WORKFLOW_STAGE,
            thread_id="thread-123",
            payload={"agent": "triage", "status": "started", "workflow_run_id": "run-123"},
        )
    )
    tool_events = rich_events_for_workflow_event(
        WorkflowEvent(
            type=event_types.TOOL_CALL,
            thread_id="thread-123",
            payload={"local_tool": "fetch_order_status", "workflow_run_id": "run-123"},
        )
    )
    hitl_events = rich_events_for_workflow_event(
        WorkflowEvent(
            type=event_types.HITL_REQUEST,
            thread_id="thread-123",
            payload={"checkpoint_id": "checkpoint-123", "workflow_run_id": "run-123"},
        )
    )
    output_events = rich_events_for_workflow_event(
        WorkflowEvent(
            type=event_types.WORKFLOW_OUTPUT,
            thread_id="thread-123",
            payload={"message": "done", "status": "completed", "workflow_run_id": "run-123"},
        )
    )

    assert stage_events[0]["type"] == "STEP_STARTED"
    assert stage_events[0]["stepName"] == "triage"
    assert [event["type"] for event in tool_events] == [
        "TOOL_CALL_START",
        "TOOL_CALL_RESULT",
        "TOOL_CALL_END",
    ]
    assert hitl_events[0]["type"] == "CUSTOM"
    assert hitl_events[0]["name"] == "hitl.request"
    assert [event["type"] for event in output_events] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]


@pytest.mark.asyncio
async def test_event_bus_rich_stream_emits_additive_agui_envelope() -> None:
    event_bus = EventBus()
    await event_bus.publish(
        WorkflowEvent(
            type=event_types.WORKFLOW_OUTPUT,
            thread_id="thread-123",
            payload={"message": "done", "status": "completed"},
        )
    )

    stream = event_bus.rich_sse_stream("thread-123")
    try:
        chunk = await stream.__anext__()
    finally:
        await stream.aclose()

    assert chunk.startswith("event: workflow.rich\n")
    data = chunk.split("data: ", 1)[1].strip()
    envelope = json.loads(data)
    assert envelope["type"] == "workflow.rich"
    assert envelope["version"] == "ag-ui-compatible.v1"
    assert envelope["native_event"]["type"] == "workflow.output"
    assert envelope["events"][0]["type"] == "RUN_STARTED"
    assert envelope["events"][-1]["type"] == "RUN_FINISHED"
