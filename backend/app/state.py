from __future__ import annotations

import os

from app.db import postgres_db
from app.models import WorkflowEvent
from app.workflow_run_repository import WorkflowRunRepository
from tools.mcp_tools import MCPKnowledgeTool
from workflows.checkpoint_store import CheckpointStore
from workflows.event_bus import EventBus
from workflows.maf_sdk_workflow import MafSdkSequentialWorkflow
from workflows.sequential_resolution_workflow import SequentialResolutionWorkflow
from workflows.session_memory import SessionMemoryStore

postgres_db.ensure_schema()
event_bus = EventBus()
workflow_run_repository = WorkflowRunRepository()
memory_store = SessionMemoryStore()
checkpoint_store = CheckpointStore()
mcp_tool = MCPKnowledgeTool()


def _status_from_output(event: WorkflowEvent) -> str | None:
    status = event.payload.get("status")
    if not isinstance(status, str):
        return None
    if status in {"completed", "failed", "escalated"}:
        return status
    return None


def _sync_event_to_run(event: WorkflowEvent) -> None:
    workflow_run_repository.append_workflow_event(event.thread_id, event)

    if event.type == "workflow.stage":
        stage = event.payload.get("agent")
        if isinstance(stage, str):
            workflow_run_repository.update_current_stage(event.thread_id, stage)

    if event.type == "hitl.request":
        workflow_run_repository.add_pending_approval(event.thread_id, event.payload)
        workflow_run_repository.update_workflow_status(
            event.thread_id, "waiting_approval"
        )
        return

    if event.type == "hitl.response":
        checkpoint_id = event.payload.get("checkpoint_id")
        decision = event.payload.get("decision")
        reviewer = event.payload.get("reviewer")
        comments = event.payload.get("comments")
        if isinstance(checkpoint_id, str) and isinstance(decision, str):
            workflow_run_repository.resolve_approval(
                thread_id=event.thread_id,
                checkpoint_id=checkpoint_id,
                decision=decision,
                comment=comments if isinstance(comments, str) else None,
                reviewer=reviewer if isinstance(reviewer, str) else None,
            )
        workflow_run_repository.update_workflow_status(event.thread_id, "running")
        return

    if event.type == "workflow.output":
        workflow_run_repository.update_latest_output(event.thread_id, event.payload)
        output_status = _status_from_output(event)
        if output_status:
            workflow_run_repository.update_workflow_status(
                event.thread_id, output_status
            )
        else:
            workflow_run_repository.update_workflow_status(event.thread_id, "completed")
        return

    if event.type == "workflow.failed":
        workflow_run_repository.update_workflow_status(event.thread_id, "failed")


event_bus.add_listener(_sync_event_to_run)

if os.getenv("USE_MAF_SDK", "false").lower() == "true":
    try:
        workflow = MafSdkSequentialWorkflow(
            event_bus=event_bus,
            memory_store=memory_store,
            checkpoint_store=checkpoint_store,
            mcp_tool=mcp_tool,
        )
    except Exception:
        workflow = SequentialResolutionWorkflow(
            event_bus=event_bus,
            memory_store=memory_store,
            checkpoint_store=checkpoint_store,
            mcp_tool=mcp_tool,
        )
else:
    workflow = SequentialResolutionWorkflow(
        event_bus=event_bus,
        memory_store=memory_store,
        checkpoint_store=checkpoint_store,
        mcp_tool=mcp_tool,
    )
