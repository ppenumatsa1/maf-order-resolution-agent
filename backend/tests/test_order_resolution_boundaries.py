from __future__ import annotations

from typing import Any

import pytest
from app.models import ChatRunRequest, HitlResponseRequest
from app.modules.order_resolution.models import WorkflowContext, WorkflowEvent
from app.modules.order_resolution.projections import WorkflowRunEventProjector
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
